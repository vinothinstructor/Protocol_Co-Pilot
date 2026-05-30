/**
 * ProseMirror plugin that paints colored risk bars on clauses via NodeDecorations.
 *
 * Phase 2B: paints risk-bar / risk-{level} per scored clause.
 * Phase 3:  adds risk-selected on the currently selected clause.
 * Phase 5:  adds risk-scoring on clauses with a live score-request in flight.
 *
 * External code dispatches a transaction with plugin meta to update any subset of
 * { scores, selectedBlockId, scoringIds }. The plugin's apply() rebuilds its
 * DecorationSet whenever any of those change.
 */

import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { Extension } from "@tiptap/react";
import type { Node as ProsemirrorNode } from "@tiptap/pm/model";

export type RiskLevel = "high" | "medium" | "low";

export interface RiskEntry {
  riskLevel: RiskLevel;
  summary: string;
}

interface PluginState {
  scores: Map<string, RiskEntry>;
  selectedBlockId: string | null;
  scoringIds: Set<string>;
  decorations: DecorationSet;
}

export interface RiskScoreMeta {
  scores?: Record<string, RiskEntry>;
  selectedBlockId?: string | null;
  scoringIds?: string[];
}

export const riskPluginKey = new PluginKey<PluginState>("riskDecorations");

function makePill(level: RiskLevel, blockId: string): HTMLElement {
  const el = document.createElement("span");
  el.className = `risk-pill risk-pill-${level}`;
  // Tiny invisible marker so the click handler in ProtocolEditor can still
  // identify the parent clause via .closest('[data-block-id]')
  el.setAttribute("data-pill-for", blockId);
  el.setAttribute("contenteditable", "false");
  if (level === "high") el.textContent = "HIGH RISK";
  else if (level === "medium") el.textContent = "MED RISK";
  else el.textContent = "✓";
  return el;
}

function buildDecorations(
  doc: ProsemirrorNode,
  scores: Map<string, RiskEntry>,
  selectedBlockId: string | null,
  scoringIds: Set<string>
): DecorationSet {
  const decorations: Decoration[] = [];

  doc.descendants((node, pos) => {
    const blockId = node.attrs?.blockId as string | undefined;
    if (!blockId) return;

    const entry = scores.get(blockId);
    const isScoring = scoringIds.has(blockId);
    const hasScore = entry !== undefined;

    // Skip nodes with no score AND no in-flight scoring
    if (!hasScore && !isScoring) return;

    const isSelected = blockId === selectedBlockId;

    // ── Node decoration: gutter bar + classes ─────────────────────────────
    // Add the risk-bar class for HIGH/MED, the risk-scoring class for in-flight,
    // and the risk-selected class when this clause is the active panel target.
    // LOW clauses with a score get a `risk-bar` only when selected (for the
    // teal selection highlight); otherwise no bar (visually quiet).
    const showBar = (entry && entry.riskLevel !== "low") || isScoring || isSelected;
    if (showBar) {
      const classes = ["risk-bar"];
      if (entry && entry.riskLevel !== "low") classes.push(`risk-${entry.riskLevel}`);
      if (isSelected) classes.push("risk-selected");
      if (isScoring) classes.push("risk-scoring");
      decorations.push(
        Decoration.node(pos, pos + node.nodeSize, {
          class: classes.join(" "),
          title: entry?.summary ?? "Scoring this clause…",
        })
      );
    }

    // ── Widget decoration: right-edge pill ────────────────────────────────
    // For inline rendering, the widget must be placed INSIDE the paragraph
    // that holds the text — not at a block-level position between siblings.
    //
    // - Standalone paragraph (blockId on a <p>): end-of-content is at
    //     pos + nodeSize - 1   (just before </p>)
    // - List item (blockId on an <li> with inner <p>): drill into the first
    //   child paragraph; end-of-content is at
    //     pos + 1 + innerPara.nodeSize - 1   (inside the <p>, before </p>)
    //
    // Without this distinction, the widget for a listItem ends up between
    // </p> and </li>, which ProseMirror renders as a block-level sibling →
    // the pill appears on a new line below the clause.
    if (entry) {
      let pillPos: number;
      if (node.type.name === "listItem") {
        const inner = node.firstChild;
        if (inner && inner.type.name === "paragraph") {
          pillPos = pos + 1 + inner.nodeSize - 1;
        } else {
          pillPos = pos + node.nodeSize - 1;
        }
      } else {
        // paragraph (or any other inline-content block)
        pillPos = pos + node.nodeSize - 1;
      }
      const level = entry.riskLevel;
      decorations.push(
        Decoration.widget(pillPos, () => makePill(level, blockId), {
          side: 1,
          ignoreSelection: true,
          // Stable key so ProseMirror reuses the DOM node across re-renders
          key: `pill-${blockId}-${level}`,
        })
      );
    }
  });

  return DecorationSet.create(doc, decorations);
}

const riskPlugin = new Plugin<PluginState>({
  key: riskPluginKey,

  state: {
    init() {
      return {
        scores: new Map(),
        selectedBlockId: null,
        scoringIds: new Set(),
        decorations: DecorationSet.empty,
      };
    },

    apply(tr, prev) {
      const meta = tr.getMeta(riskPluginKey) as RiskScoreMeta | undefined;

      if (meta !== undefined) {
        const scores =
          meta.scores !== undefined
            ? new Map(Object.entries(meta.scores) as [string, RiskEntry][])
            : prev.scores;

        const selectedBlockId =
          meta.selectedBlockId !== undefined ? meta.selectedBlockId : prev.selectedBlockId;

        const scoringIds =
          meta.scoringIds !== undefined ? new Set(meta.scoringIds) : prev.scoringIds;

        return {
          scores,
          selectedBlockId,
          scoringIds,
          decorations: buildDecorations(tr.doc, scores, selectedBlockId, scoringIds),
        };
      }

      if (tr.docChanged) {
        // Rebuild against the new doc — ProseMirror has mapped through structural changes,
        // but new nodes (with fresh blockIds from BlockIdAssignerExtension) need a fresh decoration set
        return {
          ...prev,
          decorations: buildDecorations(tr.doc, prev.scores, prev.selectedBlockId, prev.scoringIds),
        };
      }

      return prev;
    },
  },

  props: {
    decorations(state) {
      return riskPluginKey.getState(state)?.decorations ?? DecorationSet.empty;
    },
  },
});

export const RiskDecorationExtension = Extension.create({
  name: "riskDecorations",
  addProseMirrorPlugins() {
    return [riskPlugin];
  },
});
