import { useCallback, useEffect, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import type { Node as ProsemirrorNode } from "@tiptap/pm/model";
import { scoreProtocol, type ClauseRiskResult, type SeverityCounts } from "@/lib/api";

const DEBOUNCE_MS = 600;

interface UseLiveScoringOpts {
  editor: Editor | null;
  protocolId: string;
  // Phase 5 Undo: seeded block_id → original seeded text. Used to detect which
  // clauses currently differ from their original (drives the "Undo edit" UI).
  originalTexts: Map<string, string>;
  onScoreUpdate: (
    updates: ClauseRiskResult[],
    overallRisk: number,
    severityCounts: SeverityCounts
  ) => void;
}

function normalizeText(s: string): string {
  return s.trim().replace(/\s+/g, " ");
}

/**
 * Subscribes to TipTap document changes and triggers debounced re-scoring of
 * any clause whose text changed (new or edited). Maintains a `scoring` set of
 * block_ids currently being scored — consumers render a pulse indicator from it.
 *
 * Deleted block_ids are returned via `recentlyDeleted` so the parent can drop
 * them from clauseScores.
 */
export function useLiveScoring({
  editor,
  protocolId,
  originalTexts,
  onScoreUpdate,
}: UseLiveScoringOpts) {
  const [scoringIds, setScoringIds] = useState<Set<string>>(new Set());
  const [recentlyDeleted, setRecentlyDeleted] = useState<string[]>([]);
  const [editedBlockIds, setEditedBlockIds] = useState<Set<string>>(new Set());
  const editedSnapshotRef = useRef<Set<string>>(new Set());

  const prevTextsRef = useRef<Map<string, string>>(new Map());
  const debounceTimerRef = useRef<number | null>(null);
  const pendingChangesRef = useRef<Set<string>>(new Set());
  const isInitialContentSetRef = useRef(false);

  useEffect(() => {
    if (!editor) return;

    const collectTexts = (doc: ProsemirrorNode): Map<string, string> => {
      const out = new Map<string, string>();
      doc.descendants((node) => {
        if (node.type.name !== "paragraph" && node.type.name !== "listItem") return;
        const bid = node.attrs?.blockId as string | undefined;
        if (!bid) return;
        out.set(bid, node.textContent.trim());
      });
      return out;
    };

    const fireScore = async () => {
      const changed = Array.from(pendingChangesRef.current);
      pendingChangesRef.current = new Set();
      if (changed.length === 0) return;

      const currentTexts = collectTexts(editor.state.doc);
      const clauseTexts: Record<string, string> = {};
      for (const bid of changed) {
        const text = currentTexts.get(bid);
        if (text === undefined || text === "") continue;
        clauseTexts[bid] = text;
      }
      if (Object.keys(clauseTexts).length === 0) return;

      setScoringIds((prev) => {
        const next = new Set(prev);
        Object.keys(clauseTexts).forEach((b) => next.add(b));
        return next;
      });

      try {
        const resp = await scoreProtocol(
          protocolId,
          Object.keys(clauseTexts),
          clauseTexts
        );
        onScoreUpdate(resp.clauses, resp.overall_risk, resp.severity_counts);
      } catch (e) {
        console.error("[LiveScoring] score request failed:", e);
      } finally {
        setScoringIds((prev) => {
          const next = new Set(prev);
          Object.keys(clauseTexts).forEach((b) => next.delete(b));
          return next;
        });
      }
    };

    const handleUpdate = () => {
      const currentTexts = collectTexts(editor.state.doc);

      // First update after content load: just snapshot, don't fire
      if (!isInitialContentSetRef.current) {
        prevTextsRef.current = currentTexts;
        isInitialContentSetRef.current = true;
        return;
      }

      const changed: string[] = [];
      const deleted: string[] = [];
      for (const [bid, text] of currentTexts) {
        const prev = prevTextsRef.current.get(bid);
        if (prev === undefined) {
          if (text.length > 0) changed.push(bid);
        } else if (prev !== text) {
          // A clause whose text was emptied (non-empty → "") is treated as a
          // deletion: an empty bullet contributes nothing and its prior score
          // must not linger in the aggregate. The node may still exist in the
          // doc (empty listItem), but semantically the clause is gone.
          if (text === "" && prev !== "") {
            deleted.push(bid);
          } else {
            changed.push(bid);
          }
        }
      }
      for (const bid of prevTextsRef.current.keys()) {
        if (!currentTexts.has(bid)) deleted.push(bid);
      }
      prevTextsRef.current = currentTexts;

      // Phase 5 Undo: recompute editedBlockIds for seeded blk_ blocks whose
      // current text differs from the seeded original. Only fire setState when
      // the set actually changes (set identity vs membership).
      if (originalTexts.size > 0) {
        const edited = new Set<string>();
        for (const [bid, text] of currentTexts) {
          if (!bid.startsWith("blk_")) continue;
          const orig = originalTexts.get(bid);
          if (orig !== undefined && normalizeText(text) !== normalizeText(orig)) {
            edited.add(bid);
          }
        }
        const prev = editedSnapshotRef.current;
        let same = edited.size === prev.size;
        if (same) {
          for (const id of edited) {
            if (!prev.has(id)) { same = false; break; }
          }
        }
        if (!same) {
          editedSnapshotRef.current = edited;
          setEditedBlockIds(edited);
        }
      }

      if (deleted.length > 0) setRecentlyDeleted(deleted);
      if (changed.length === 0) return;

      changed.forEach((b) => pendingChangesRef.current.add(b));
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
      }
      debounceTimerRef.current = window.setTimeout(() => {
        debounceTimerRef.current = null;
        void fireScore();
      }, DEBOUNCE_MS);
    };

    editor.on("update", handleUpdate);

    return () => {
      editor.off("update", handleUpdate);
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, [editor, protocolId, onScoreUpdate, originalTexts]);

  // Reset the initial-snapshot flag when editor reloads content from the API.
  // Memoized so consumers can list it in useEffect deps without infinite re-runs.
  const resetInitialSnapshot = useCallback(() => {
    isInitialContentSetRef.current = false;
    prevTextsRef.current = new Map();
  }, []);

  // Pre-acknowledge that a block's text just changed to a known value, so the
  // next handleUpdate's diff sees no change and the debounce skips it.
  // Used by handleAccept to prevent the live-scorer from racing the accept-fix
  // response and overwriting it with a heuristic-derived result.
  const ackBlockText = useCallback((blockId: string, text: string) => {
    prevTextsRef.current.set(blockId, text.trim());
    pendingChangesRef.current.delete(blockId);
  }, []);

  return { scoringIds, recentlyDeleted, editedBlockIds, resetInitialSnapshot, ackBlockText };
}
