import { useEffect, useState, forwardRef, useImperativeHandle, useCallback, useRef } from "react";
import { useEditor, EditorContent, BubbleMenu } from "@tiptap/react";
import { Bold, Italic, List } from "lucide-react";
import { buildProtocolExtensions } from "@/lib/tiptap/schema";
import { riskPluginKey, type RiskEntry } from "@/lib/tiptap/RiskDecorationPlugin";
import { fetchProtocol, type Protocol, type ClauseRiskResult, type SeverityCounts } from "@/lib/api";
import { useLiveScoring } from "@/hooks/useLiveScoring";

export interface SelectedClauseInfo {
  blockId: string;
  clauseText: string;
  sectionLabel: string;
}

// Ref API — lets EditorPage replace clause text after an Accept fix or Undo Edit
export interface ProtocolEditorRef {
  replaceClauseText: (blockId: string, newText: string) => void;
  restoreClauseToOriginal: (blockId: string) => void;
  ackBlockText: (blockId: string, text: string) => void;
  // Drafting Agent: insert a new listItem at the end of the given section.
  insertClauseAtSection: (sectionId: string, clauseText: string) => void;
  // Gap detection: current per-section combined text from the live editor.
  // Lets gap re-detection reflect unsaved edits/deletions, not the seeded DB doc.
  getSectionTexts: () => Record<string, string>;
}

interface Props {
  protocolId: string;
  clauseScores: Map<string, ClauseRiskResult>;
  selectedBlockId: string | null;
  onClauseSelect: (info: SelectedClauseInfo) => void;
  onLiveScoreUpdate: (
    updates: ClauseRiskResult[],
    overallRisk: number,
    severityCounts: SeverityCounts
  ) => void;
  onClausesDeleted: (blockIds: string[]) => void;
  onEditedBlocksChange?: (editedBlockIds: Set<string>) => void;
  // Drafting Agent: called when the user clicks the + button on a clause section heading
  onSectionDraftClick?: (sectionId: string) => void;
}

function buildOriginalTexts(protocol: Protocol): Map<string, string> {
  const m = new Map<string, string>();
  for (const section of protocol.sections) {
    for (const block of section.blocks) {
      m.set(block.block_id, block.text);
    }
  }
  return m;
}

function buildTipTapContent(protocol: Protocol) {
  const content: object[] = [];
  for (const section of protocol.sections) {
    content.push({
      type: "heading",
      attrs: { level: 2 },
      content: [{ type: "text", text: `${section.number}. ${section.heading}` }],
    });
    const clauseBlocks = section.blocks.filter((b) => b.type === "clause");
    const paragraphBlocks = section.blocks.filter((b) => b.type === "paragraph");
    for (const block of paragraphBlocks) {
      content.push({
        type: "paragraph",
        attrs: { blockId: block.block_id },
        content: [{ type: "text", text: block.text }],
      });
    }
    if (clauseBlocks.length > 0) {
      content.push({
        type: "bulletList",
        content: clauseBlocks.map((block) => ({
          type: "listItem",
          attrs: { blockId: block.block_id },
          content: [{ type: "paragraph", content: [{ type: "text", text: block.text }] }],
        })),
      });
    }
  }
  return { type: "doc", content };
}

function getSectionLabel(blockEl: HTMLElement): string {
  const tiptapDoc = blockEl.closest(".tiptap-doc");
  if (!tiptapDoc) return "";
  let ancestor: HTMLElement | null = blockEl;
  while (ancestor && ancestor.parentElement !== tiptapDoc) {
    ancestor = ancestor.parentElement;
  }
  if (!ancestor) return "";
  let sibling: Element | null = ancestor.previousElementSibling;
  while (sibling) {
    if (sibling.tagName === "H2") return sibling.textContent?.trim() ?? "";
    sibling = sibling.previousElementSibling;
  }
  return "";
}

const ProtocolEditor = forwardRef<ProtocolEditorRef, Props>(
  ({ protocolId, clauseScores, selectedBlockId, onClauseSelect, onLiveScoreUpdate, onClausesDeleted, onEditedBlocksChange, onSectionDraftClick }, ref) => {
    const [protocol, setProtocol] = useState<Protocol | null>(null);
    const [originalTexts, setOriginalTexts] = useState<Map<string, string>>(new Map());
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    // Stable wrapper ref so the extension always calls the latest onSectionDraftClick
    // even though extensions are only initialized once at editor creation.
    const draftClickRef = useRef(onSectionDraftClick);
    useEffect(() => { draftClickRef.current = onSectionDraftClick; }, [onSectionDraftClick]);
    const stableDraftClick = useCallback((sectionId: string) => {
      draftClickRef.current?.(sectionId);
    }, []);

    const editor = useEditor({
      extensions: buildProtocolExtensions(stableDraftClick),
      editable: true,
      editorProps: { attributes: { class: "tiptap-doc" } },
    });

    // Stable callback so useLiveScoring doesn't re-subscribe every render
    const handleScoreUpdate = useCallback(
      (updates: ClauseRiskResult[], overall: number, sev: SeverityCounts) => {
        onLiveScoreUpdate(updates, overall, sev);
      },
      [onLiveScoreUpdate]
    );

    const { scoringIds, recentlyDeleted, editedBlockIds, resetInitialSnapshot, ackBlockText } = useLiveScoring({
      editor,
      protocolId,
      originalTexts,
      onScoreUpdate: handleScoreUpdate,
    });


    // Propagate editedBlockIds to parent
    useEffect(() => {
      onEditedBlocksChange?.(editedBlockIds);
    }, [editedBlockIds, onEditedBlocksChange]);

    // Keep a ref to editedBlockIds so the click handler closure stays fresh
    const editedBlockIdsRef = useRef<Set<string>>(new Set());
    useEffect(() => {
      editedBlockIdsRef.current = editedBlockIds;
    }, [editedBlockIds]);

    // Propagate deletions to parent and update bar accordingly
    useEffect(() => {
      if (recentlyDeleted.length > 0) onClausesDeleted(recentlyDeleted);
    }, [recentlyDeleted, onClausesDeleted]);

    // Push scoringIds set into the decoration plugin (drives the pulse class)
    useEffect(() => {
      if (!editor) return;
      const tr = editor.state.tr.setMeta(riskPluginKey, { scoringIds: Array.from(scoringIds) });
      editor.view.dispatch(tr);
    }, [editor, scoringIds]);

    // Expose replaceClauseText + restoreClauseToOriginal to parent via ref
    useImperativeHandle(ref, () => ({
      replaceClauseText: (blockId: string, newText: string) => {
        if (!editor) return;
        editor.commands.command(({ tr, state }) => {
          let replaced = false;
          state.doc.descendants((node, pos) => {
            if (replaced) return false;
            if (node.attrs?.blockId !== blockId) return;

            if (node.type.name === "listItem") {
              const para = node.firstChild;
              if (!para) return false;
              const paraPos = pos + 1;
              const textNode = state.schema.text(newText);
              tr.replaceWith(paraPos + 1, paraPos + para.nodeSize - 1, textNode);
              replaced = true;
              return false;
            }
            if (node.type.name === "paragraph") {
              const textNode = state.schema.text(newText);
              tr.replaceWith(pos + 1, pos + node.nodeSize - 1, textNode);
              replaced = true;
              return false;
            }
          });
          return replaced;
        });
      },
      ackBlockText: (blockId: string, text: string) => ackBlockText(blockId, text),
      restoreClauseToOriginal: (blockId: string) => {
        const original = originalTexts.get(blockId);
        if (!original || !editor) return;
        editor.commands.command(({ tr, state }) => {
          let replaced = false;
          state.doc.descendants((node, pos) => {
            if (replaced) return false;
            if (node.attrs?.blockId !== blockId) return;
            if (node.type.name === "listItem") {
              const para = node.firstChild;
              if (!para) return false;
              const paraPos = pos + 1;
              tr.replaceWith(paraPos + 1, paraPos + para.nodeSize - 1, state.schema.text(original));
              replaced = true;
              return false;
            }
            if (node.type.name === "paragraph") {
              tr.replaceWith(pos + 1, pos + node.nodeSize - 1, state.schema.text(original));
              replaced = true;
              return false;
            }
          });
          return replaced;
        });
      },

      insertClauseAtSection: (sectionId: string, clauseText: string) => {
        if (!editor) return;
        const sectionNum = parseInt(sectionId.replace("sec_", ""));
        if (![4, 5, 6].includes(sectionNum)) return;
        const prefix = `${sectionNum}.`;

        editor.commands.command(({ state, dispatch }) => {
          let insertPos: number | null = null;
          let afterTarget = false;

          // Walk top-level doc children. offset = cumulative size within doc content.
          // Absolute position = 1 (doc-open token) + offset.
          state.doc.forEach((node, offset) => {
            if (insertPos !== null) return;
            if (node.type.name === "heading") {
              afterTarget = node.textContent.startsWith(prefix);
            } else if (afterTarget && node.type.name === "bulletList") {
              // Insert just before the bulletList's closing tag
              insertPos = 1 + offset + node.nodeSize - 1;
              afterTarget = false;
            } else if (afterTarget) {
              afterTarget = false;
            }
          });

          if (insertPos === null) return false;

          const newItem = state.schema.nodes.listItem.create(
            { blockId: null }, // BlockIdAssignerExtension will assign gen_ id
            state.schema.nodes.paragraph.create(
              null,
              clauseText ? state.schema.text(clauseText) : undefined
            )
          );
          dispatch?.(state.tr.insert(insertPos, newItem));
          return true;
        });

        // Scroll the newly inserted clause into view after a tick
        setTimeout(() => {
          const items = document.querySelectorAll(
            `[data-block-id^="gen_"]`
          );
          const last = items[items.length - 1] as HTMLElement | null;
          last?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 100);
      },

      getSectionTexts: () => {
        const result: Record<string, string> = {};
        if (!editor) return result;
        let currentSection: string | null = null;
        editor.state.doc.forEach((node) => {
          if (node.type.name === "heading") {
            const m = node.textContent.match(/^(\d+)\./);
            currentSection = m ? `sec_${m[1]}` : null;
          } else if (currentSection) {
            result[currentSection] =
              (result[currentSection] ?? "") + " " + node.textContent;
          }
        });
        return result;
      },
    }), [editor, originalTexts, ackBlockText]);

    useEffect(() => {
      fetchProtocol("DIABETES-2026-PH3")
        .then((resp) => {
          setProtocol(resp.document);
          setOriginalTexts(buildOriginalTexts(resp.document));
        })
        .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
        .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
      if (editor && protocol) {
        resetInitialSnapshot();           // mark "next onUpdate is the initial snapshot — don't score"
        editor.commands.setContent(buildTipTapContent(protocol));
      }
    }, [editor, protocol, resetInitialSnapshot]);

    useEffect(() => {
      if (!editor || clauseScores.size === 0) return;
      const scoreMap: Record<string, RiskEntry> = {};
      clauseScores.forEach((result, blockId) => {
        scoreMap[blockId] = { riskLevel: result.risk_level, summary: result.summary };
      });
      const tr = editor.state.tr.setMeta(riskPluginKey, { scores: scoreMap, selectedBlockId });
      editor.view.dispatch(tr);
    }, [editor, clauseScores]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
      if (!editor) return;
      const tr = editor.state.tr.setMeta(riskPluginKey, { selectedBlockId });
      editor.view.dispatch(tr);
    }, [editor, selectedBlockId]);

    const handleEditorClick = (e: React.MouseEvent<HTMLDivElement>) => {
      const target = e.target as HTMLElement;
      const blockEl = target.closest("[data-block-id]") as HTMLElement | null;
      if (!blockEl) return;
      const blockId = blockEl.getAttribute("data-block-id");
      if (!blockId) return;
      const isRisky =
        blockEl.classList.contains("risk-high") || blockEl.classList.contains("risk-medium");
      // Allow opening the panel for: HIGH/MED clauses (current behavior) OR
      // seeded clauses that have been edited (so the user can hit Undo Edit).
      const isEditedSeeded = blockId.startsWith("blk_") && editedBlockIdsRef.current.has(blockId);
      if (!isRisky && !isEditedSeeded) return;
      const clauseText = blockEl.textContent?.trim() ?? "";
      const sectionLabel = getSectionLabel(blockEl);
      onClauseSelect({ blockId, clauseText, sectionLabel });
    };

    if (loading) {
      return (
        <div className="flex items-center justify-center h-full text-slate-400 text-sm">
          Loading protocol…
        </div>
      );
    }
    if (error) {
      return (
        <div className="flex items-center justify-center h-full text-red-500 text-sm px-8">
          <div>
            <p className="font-semibold">Failed to load protocol</p>
            <p className="text-xs mt-1 text-red-400">{error}</p>
          </div>
        </div>
      );
    }

    return (
      <div className="h-full overflow-y-auto bg-white" onClick={handleEditorClick}>
        <div className="px-16 py-10">
          <div className="max-w-3xl mx-auto">
            {protocol && (
              <div className="mb-8 pb-6 border-b border-slate-200">
                <h1 className="text-xl font-bold leading-snug mb-2" style={{ color: "#1a2744" }}>
                  {protocol.title}
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  {protocol.protocol_id} · {protocol.version} · {protocol.therapeutic_area}
                </p>
              </div>
            )}
            <EditorContent editor={editor} />
            {editor && (
              <BubbleMenu
                editor={editor}
                tippyOptions={{ duration: 100, placement: "top" }}
              >
                <div className="flex items-center gap-0.5 rounded-md border border-slate-200 bg-white p-1 shadow-lg">
                  <ToolbarButton
                    onClick={() => editor.chain().focus().toggleBold().run()}
                    active={editor.isActive("bold")}
                    label="Bold (⌘B)"
                  >
                    <Bold size={14} strokeWidth={2.25} />
                  </ToolbarButton>
                  <ToolbarButton
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                    active={editor.isActive("italic")}
                    label="Italic (⌘I)"
                  >
                    <Italic size={14} strokeWidth={2.25} />
                  </ToolbarButton>
                  <ToolbarButton
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                    active={editor.isActive("bulletList")}
                    label="Bullet list"
                  >
                    <List size={14} strokeWidth={2.25} />
                  </ToolbarButton>
                </div>
              </BubbleMenu>
            )}
          </div>
        </div>
      </div>
    );
  }
);

// Small button used in the BubbleMenu toolbar. Navy on white default; teal-tinted
// background when the formatting mark is active at the current selection.
function ToolbarButton({
  onClick, active, children, label,
}: {
  onClick: () => void;
  active: boolean;
  children: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`w-7 h-7 inline-flex items-center justify-center rounded transition-colors ${
        active
          ? "bg-teal-50 text-teal-700"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      {children}
    </button>
  );
}

ProtocolEditor.displayName = "ProtocolEditor";
export default ProtocolEditor;
