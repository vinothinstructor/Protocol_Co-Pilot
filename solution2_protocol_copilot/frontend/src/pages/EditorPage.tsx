import { useState, useEffect, useRef, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import AppChrome from "@/components/AppChrome";
import RiskStatusBar from "@/components/RiskStatusBar";
import ProtocolEditor, {
  type ProtocolEditorRef,
  type SelectedClauseInfo,
} from "@/components/ProtocolEditor";
import IssuePanel from "@/components/IssuePanel";
import ExportModal from "@/components/ExportModal";
import FeasibilityToast from "@/components/FeasibilityToast";
import FeasibilityPanel from "@/components/FeasibilityPanel";
import FeasibilityErrorToast from "@/components/FeasibilityErrorToast";
import DraftClausePopover from "@/components/DraftClausePopover";
import DraftSuccessToast from "@/components/DraftSuccessToast";
import GapDetectionPanel from "@/components/GapDetectionPanel";
import FloatingDeltaChip from "@/components/FloatingDeltaChip";
import { getLastAcceptButtonRect } from "@/components/IssuePanel";
import { useProtocolScore } from "@/hooks/useProtocolScore";
import { acceptFix, dismissFix, fetchFeasibility, draftClause, detectGaps, type FixCandidate, type ClauseRiskResult, type SeverityCounts } from "@/lib/api";
import { useFeasibilityStore, buildToastDelta } from "@/stores/feasibilityStore";
import { useDraftingStore } from "@/stores/draftingStore";
import { useModeStore } from "@/stores/modeStore";

const PROTOCOL_ID = "DIABETES-2026-PH3";

function PanelPlaceholder({ counts }: { counts: SeverityCounts }) {
  // Headline detection line — live, updates when severityCounts change
  const detectedLine =
    counts.high > 0
      ? `${counts.high} high-risk clause${counts.high === 1 ? "" : "s"} detected in your draft.`
      : counts.medium > 0
      ? `${counts.medium} medium-risk clause${counts.medium === 1 ? "" : "s"} flagged in your draft.`
      : "Your protocol is in good shape — no flagged clauses.";

  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center px-8 max-w-sm">
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
          style={{ background: "rgba(20, 184, 166, 0.12)" }}
        >
          <Sparkles size={28} className="text-teal-600" strokeWidth={2} />
        </div>
        <p className="text-lg font-bold leading-snug" style={{ color: "#1a2744" }}>
          Protocol Co-Pilot is monitoring your protocol
        </p>
        <p className="text-sm text-slate-500 mt-2 leading-relaxed">
          {detectedLine}
          <br />
          Click any flagged clause to see the risk breakdown and suggested fixes.
        </p>
        <div className="flex items-stretch gap-2 mt-8 justify-center">
          <StatTile color="#dc2626" label="HIGH" value={counts.high} />
          <StatTile color="#d97706" label="MED" value={counts.medium} />
          <StatTile color="#16a34a" label="LOW" value={counts.low} />
        </div>
      </div>
    </div>
  );
}

function StatTile({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <div className="flex flex-col items-center justify-center min-w-[64px] rounded-md border border-slate-200 bg-white px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ background: color }} />
        <span className="text-[9px] font-semibold text-slate-500 tracking-widest">{label}</span>
      </div>
      <span className="text-lg font-bold tabular-nums" style={{ color }}>
        {value}
      </span>
    </div>
  );
}

export default function EditorPage() {
  const {
    clauseScores, overallRisk, severityCounts, loading,
    updateClauseScore, setOverallRisk, setSeverityCounts,
    mergeClauseScoresAndRecompute, removeClauseScoresAndRecompute,
  } = useProtocolScore(PROTOCOL_ID);

  const {
    currentProjection,
    panelOpen,
    setProjection,
    clearProjection,
    setBaseline,
    setLastToastDelta,
    setFeasibilityError,
  } = useFeasibilityStore();

  const selectedMode = useModeStore((s) => s.selectedMode);
  const { setGaps, setGapsLoading, setGapPanelOpen } = useDraftingStore();

  const [selectedClause, setSelectedClause] = useState<SelectedClauseInfo | null>(null);
  const editorRef = useRef<ProtocolEditorRef>(null);

  // Gap re-detection debounce — fires 1.5s after an edit/deletion. Sends the live
  // editor's per-section text so the requirement checklist reflects unsaved edits:
  // removing the clause that satisfied a requirement re-surfaces that gap.
  const gapRedetectTimerRef = useRef<number | null>(null);
  const triggerGapRedetection = useCallback(() => {
    if (gapRedetectTimerRef.current !== null) window.clearTimeout(gapRedetectTimerRef.current);
    gapRedetectTimerRef.current = window.setTimeout(() => {
      gapRedetectTimerRef.current = null;
      const sectionTexts = editorRef.current?.getSectionTexts();
      detectGaps(PROTOCOL_ID, sectionTexts)
        .then((resp) => setGaps(resp.gaps_detected))
        .catch(() => {}); // silent — gap re-detection is best-effort
    }, 1500);
  }, [setGaps]);

  // Track which clauses have been fixed so we can compute "Next Issue"
  const fixedBlockIds = useRef<Set<string>>(new Set());

  // Phase 5 Undo: which seeded blocks currently differ from their original
  const [editedBlockIds, setEditedBlockIds] = useState<Set<string>>(new Set());

  // Phase 7: count of fixes accepted in this session. Drives Export button
  // visibility (≥ 1 + 0 HIGH = show Export). Resets on page refresh.
  // We don't derive from the backend's `version` field because version now
  // bumps only on amendment-package generation, not per accept.
  const [acceptedFixesCount, setAcceptedFixesCount] = useState(0);

  // Phase 7: Export modal open state
  const [exportOpen, setExportOpen] = useState(false);

  // Drafting Agent state
  const [draftPopoverOpen, setDraftPopoverOpen] = useState(false);
  const [draftSectionId, setDraftSectionId] = useState<string | null>(null);
  const [draftSuccessMessage, setDraftSuccessMessage] = useState<string | null>(null);

  // Accept-fix path animation state
  const [floatingChip, setFloatingChip] = useState<{
    delta: number;
    fromRect: DOMRect;
    toRect: DOMRect;
  } | null>(null);

  const handleClauseSelect = (info: SelectedClauseInfo) => {
    // Clicking a clause closes the gap panel (mutual exclusion)
    setGapPanelOpen(false);
    setSelectedClause(info);
  };
  const handleClose = () => setSelectedClause(null);

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setSelectedClause(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Fetch baseline feasibility projection once on mount (after protocol loads)
  useEffect(() => {
    if (loading) return;
    fetchFeasibility(PROTOCOL_ID)
      .then((proj) => {
        setBaseline(proj);
        setProjection(proj);
      })
      .catch((err: Error) => {
        // Baseline fetch failure is surfaced as an error only if we're in LIVE mode.
        // In FAKE/MOCK/CACHED, a startup failure is unexpected — still surface it.
        setFeasibilityError(err.message);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // Re-fetch when the panel opens OR when mode changes while the panel is open.
  useEffect(() => {
    if (!panelOpen) return;
    fetchFeasibility(PROTOCOL_ID)
      .then((proj) => setProjection(proj))
      .catch((err: Error) => {
        clearProjection();
        setFeasibilityError(err.message);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelOpen, selectedMode]);

  // Fetch requirement-checklist gaps once after the protocol finishes loading.
  useEffect(() => {
    if (loading) return;
    setGapsLoading(true);
    detectGaps(PROTOCOL_ID)
      .then((resp) => setGaps(resp.gaps_detected))
      .catch((err: Error) => {
        setGaps([]);
        setFeasibilityError(err.message);
      })
      .finally(() => setGapsLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  // Find the next highest-risk unfixed clause
  const findNextClause = useCallback((): SelectedClauseInfo | null => {
    const candidates: Array<{ blockId: string; score: number; level: string }> = [];
    clauseScores.forEach((result, blockId) => {
      if (!fixedBlockIds.current.has(blockId) && result.risk_level !== "low") {
        candidates.push({ blockId, score: result.score, level: result.risk_level });
      }
    });
    candidates.sort((a, b) => {
      if (a.level !== b.level) return a.level === "high" ? -1 : 1;
      return b.score - a.score;
    });
    if (candidates.length === 0) return null;

    const next = candidates[0];
    // Scroll into view and get text from DOM
    const el = document.querySelector(`[data-block-id="${next.blockId}"]`) as HTMLElement | null;
    if (!el) return null;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    const clauseText = el.textContent?.trim() ?? "";

    // Section label from preceding h2
    let sectionLabel = "";
    const tiptapDoc = el.closest(".tiptap-doc");
    if (tiptapDoc) {
      let ancestor: HTMLElement | null = el;
      while (ancestor && ancestor.parentElement !== tiptapDoc) ancestor = ancestor.parentElement;
      let sibling: Element | null = ancestor?.previousElementSibling ?? null;
      while (sibling) {
        if (sibling.tagName === "H2") { sectionLabel = sibling.textContent?.trim() ?? ""; break; }
        sibling = sibling.previousElementSibling;
      }
    }
    return { blockId: next.blockId, clauseText, sectionLabel };
  }, [clauseScores]);

  // Accept-fix handler — orchestrates the visual sequence
  const handleAccept = useCallback(async (candidate: FixCandidate) => {
    if (!selectedClause) return;
    const { blockId } = selectedClause;

    // Step A: tell live-scorer the new text BEFORE dispatching, so its next
    // handleUpdate sees prev=new and doesn't schedule a redundant score that
    // would race the accept-fix response and override it with a heuristic-
    // derived MEDIUM (the candidate text can still contain keywords that
    // trigger the heuristic, e.g., "questionnaire" + "native language" in a
    // negation context).
    editorRef.current?.ackBlockText(blockId, candidate.new_text);
    editorRef.current?.replaceClauseText(blockId, candidate.new_text);

    // Step B+C: call backend, update clause-level score immediately.
    // Overall risk + severity counts are delayed by 700ms to sync with the
    // path-animation chip that travels from the Accept button to the score badge.
    const resp = await acceptFix(PROTOCOL_ID, blockId, candidate.candidate_id);
    updateClauseScore(blockId, resp.new_clause_score);

    // Launch path animation: chip flies from Accept button → status bar score
    const fromRect = getLastAcceptButtonRect();
    const scoreEl = document.querySelector("[data-risk-score]");
    const toRect = scoreEl?.getBoundingClientRect() ?? null;
    if (fromRect && toRect) {
      setFloatingChip({ delta: candidate.delta_overall, fromRect, toRect });
    }

    fixedBlockIds.current.add(blockId);

    // Delay overall risk update so score tween fires as chip arrives (~700ms)
    setTimeout(() => {
      setOverallRisk(resp.new_overall_risk);
      setSeverityCounts(resp.new_severity_counts);
      setAcceptedFixesCount((c) => c + 1);
    }, fromRect && toRect ? 700 : 0);

    // Fetch feasibility after chip animation (700ms) + score tween (~850ms) = ~1600ms.
    // Falls back to 950ms if no animation was shown.
    const animDelay = fromRect && toRect ? 700 : 0;
    const prevProjection = currentProjection;
    setTimeout(() => {
      fetchFeasibility(PROTOCOL_ID)
        .then((newProj) => {
          setProjection(newProj);
          if (prevProjection) {
            setLastToastDelta(buildToastDelta(prevProjection, newProj));
          } else {
            setLastToastDelta(newProj);
          }
        })
        .catch((err: Error) => {
          clearProjection();
          setFeasibilityError(err.message);
        });
    }, animDelay + 950);
  }, [selectedClause, updateClauseScore, setOverallRisk, setSeverityCounts,
      currentProjection, setProjection, setLastToastDelta, clearProjection, setFeasibilityError]);

  // Phase 5: live-edit score update handler. We recompute overall + severity from
  // the client score map rather than trusting the backend's counts, because the
  // backend doesn't know about clauses deleted client-side — trusting it would
  // reset a count that a sibling deletion already lowered. (newOverall/newSev are
  // intentionally ignored here for that reason.)
  const handleLiveScoreUpdate = useCallback(
    (updates: ClauseRiskResult[], _newOverall: number, _newSev: SeverityCounts) => {
      mergeClauseScoresAndRecompute(updates);
      // Re-evaluate gaps in case edited text no longer satisfies checklist keywords
      triggerGapRedetection();
    },
    [mergeClauseScoresAndRecompute, triggerGapRedetection]
  );

  // When a clause is deleted: remove from scores + recompute aggregates from the
  // client map (respects the deletion), then re-detect gaps.
  const handleClausesDeleted = useCallback(
    (blockIds: string[]) => {
      if (blockIds.length === 0) return;
      removeClauseScoresAndRecompute(blockIds);
      // Re-run the requirement checklist against the live editor text: removing a
      // clause that satisfied a requirement (e.g. BMI eligibility) re-surfaces
      // that gap, the same way the 3 standard gaps appear.
      triggerGapRedetection();
    },
    [removeClauseScoresAndRecompute, triggerGapRedetection]
  );

  // Phase 5 Undo: parent observes edited blocks (for IssuePanel Undo Edit affordance)
  const handleEditedBlocksChange = useCallback((ids: Set<string>) => {
    setEditedBlockIds(ids);
  }, []);

  const handleUndoEdit = useCallback(() => {
    if (!selectedClause) return;
    editorRef.current?.restoreClauseToOriginal(selectedClause.blockId);
    // The text replacement triggers a TipTap update → live-scoring debounce →
    // revert detection in score.py returns the scripted score (back to HIGH).
  }, [selectedClause]);

  // Dismiss handler
  const handleDismiss = useCallback(async () => {
    if (!selectedClause) return;
    try {
      await dismissFix(PROTOCOL_ID, selectedClause.blockId);
    } catch (e) {
      console.error("Dismiss failed:", e);
    }
  }, [selectedClause]);

  // Drafting Agent handlers
  const handleSectionDraftClick = useCallback((sectionId: string) => {
    setDraftSectionId(sectionId);
    setDraftPopoverOpen(true);
  }, []);

  const handleDraftGenerate = useCallback(async (topic: string, sectionId: string) => {
    // Throws on error — popover's catch block keeps it open and re-throws so DraftClausePopover
    // sets generating=false. We surface the error via the existing FeasibilityErrorToast.
    try {
      const resp = await draftClause(PROTOCOL_ID, topic, sectionId);
      editorRef.current?.insertClauseAtSection(sectionId, resp.clause_text);
      setDraftPopoverOpen(false);
      setDraftSuccessMessage("Clause generated and scored by Protocol Co-Pilot");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Drafting failed. Please try again.";
      setFeasibilityError(msg);
      throw err; // re-throw so popover knows to stop its loading state
    }
  }, [setFeasibilityError]);

  // After success, auto-select next clause
  const handleNextIssue = useCallback(() => {
    const next = findNextClause();
    if (next) setTimeout(() => setSelectedClause(next), 150);
    else setSelectedClause(null);
  }, [findNextClause]);

  const selectedResult = selectedClause
    ? clauseScores.get(selectedClause.blockId) ?? null
    : null;

  // Compute "Clause N of M {level}-risk" subtitle for the panel header.
  // Uses document order (block_id order from the scored list) so the position
  // reflects scroll order in the editor, not score order.
  const positionLabel = (() => {
    if (!selectedClause || !selectedResult) return undefined;
    const level = selectedResult.risk_level;
    if (level === "low") return undefined;
    const sameLevel: string[] = [];
    clauseScores.forEach((r, id) => {
      if (r.risk_level === level) sameLevel.push(id);
    });
    sameLevel.sort();  // document order via stable block_id sort
    const idx = sameLevel.indexOf(selectedClause.blockId);
    if (idx < 0) return undefined;
    return `Clause ${idx + 1} of ${sameLevel.length} ${level}-risk`;
  })();

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AppChrome />
      <RiskStatusBar
        overallRisk={overallRisk}
        severityCounts={severityCounts}
        loading={loading}
        acceptedFixesCount={acceptedFixesCount}
        onExportClick={() => setExportOpen(true)}
      />
      <ExportModal
        protocolId={PROTOCOL_ID}
        open={exportOpen}
        onClose={() => setExportOpen(false)}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left panel — editor */}
        <div className="flex-[3] overflow-hidden border-r border-slate-200">
          <ProtocolEditor
            ref={editorRef}
            protocolId={PROTOCOL_ID}
            clauseScores={clauseScores}
            selectedBlockId={selectedClause?.blockId ?? null}
            onClauseSelect={handleClauseSelect}
            onLiveScoreUpdate={handleLiveScoreUpdate}
            onClausesDeleted={handleClausesDeleted}
            onEditedBlocksChange={handleEditedBlocksChange}
            onSectionDraftClick={handleSectionDraftClick}
          />
        </div>

        {/* Right panel — issue detail + feasibility panel overlay */}
        <div className="flex-[2] overflow-hidden bg-slate-50 relative">
          <AnimatePresence mode="wait">
            {selectedClause && selectedResult ? (
              <motion.div key={selectedClause.blockId} className="absolute inset-0"
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.18, ease: "easeOut" }}>
                <IssuePanel
                  blockId={selectedClause.blockId}
                  clauseText={selectedClause.clauseText}
                  sectionLabel={selectedClause.sectionLabel}
                  result={selectedResult}
                  positionLabel={positionLabel}
                  isEdited={editedBlockIds.has(selectedClause.blockId)}
                  onClose={handleClose}
                  onAccept={handleAccept}
                  onDismiss={handleDismiss}
                  onUndoEdit={handleUndoEdit}
                  onNextIssue={handleNextIssue}
                />
              </motion.div>
            ) : (
              <motion.div key="placeholder" className="absolute inset-0"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}>
                <PanelPlaceholder counts={severityCounts} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Feasibility panel slides over the issue panel */}
          <FeasibilityPanel />

          {/* Gap Detection panel — mutual exclusion with feasibility handled in RiskStatusBar */}
          <GapDetectionPanel
            protocolId={PROTOCOL_ID}
            onInsertClause={(sectionId, clauseText) => {
              editorRef.current?.insertClauseAtSection(sectionId, clauseText);
            }}
          />
        </div>
      </div>

      {/* Drafting Agent popover */}
      <DraftClausePopover
        open={draftPopoverOpen}
        sectionId={draftSectionId}
        onClose={() => setDraftPopoverOpen(false)}
        onGenerate={handleDraftGenerate}
      />

      {/* Draft success toast — fixed bottom-right above feasibility toast */}
      <DraftSuccessToast
        message={draftSuccessMessage}
        onDismiss={() => setDraftSuccessMessage(null)}
      />

      {/* Feasibility toast — fixed bottom-right (success path) */}
      <FeasibilityToast />

      {/* Feasibility/drafting error toast — fixed top-right (error path) */}
      <FeasibilityErrorToast />

      {/* Accept-fix path animation chip */}
      {floatingChip && (
        <FloatingDeltaChip
          delta={floatingChip.delta}
          fromRect={floatingChip.fromRect}
          toRect={floatingChip.toRect}
          onComplete={() => setFloatingChip(null)}
        />
      )}
    </div>
  );
}
