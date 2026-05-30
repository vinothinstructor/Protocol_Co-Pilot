import { useEffect, useRef, useState } from "react";
import { suggestFix as apiSuggestFix } from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import type { ClauseRiskResult, FixCandidate } from "@/lib/api";

// Module-level slot so the animation in EditorPage can read the Accept button's
// screen position without prop threading through multiple layers.
let _lastAcceptButtonRect: DOMRect | null = null;
export function getLastAcceptButtonRect(): DOMRect | null {
  return _lastAcceptButtonRect;
}

interface Props {
  blockId: string;
  clauseText: string;
  sectionLabel: string;
  result: ClauseRiskResult;
  // Position context: this clause is the Nth of M flagged clauses at its risk level
  positionLabel?: string;
  // Phase 5: true if this seeded clause's current text differs from its original
  isEdited?: boolean;
  onClose: () => void;
  onAccept: (candidate: FixCandidate) => Promise<void>;
  onDismiss: () => void;
  onUndoEdit?: () => void;
  onNextIssue?: () => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const FACTOR_LABELS: Record<string, string> = {
  pattern_match_strength: "Pattern match strength",
  therapeutic_area_fit: "Therapeutic area fit",
  operational_complexity: "Operational complexity",
  inclusion_restrictiveness: "Inclusion restrictiveness",
  endpoint_instrument_validation: "Instrument validation",
  visit_burden: "Visit burden",
};

function barColor(score: number): string {
  if (score >= 60) return "#ef4444";
  if (score >= 30) return "#f59e0b";
  return "#22c55e";
}
function riskColor(level: string) { return level === "high" ? "#ef4444" : "#f59e0b"; }
function riskBg(level: string) {
  return level === "high" ? "rgba(239,68,68,0.10)" : "rgba(245,158,11,0.10)";
}

// ── Sub-views ──────────────────────────────────────────────────────────────────

function AnalysisView({
  clauseText, sectionLabel, result, positionLabel,
  isEdited, onUndoEdit, onClose,
  onSuggestFix, onDismiss, suggestLoading,
  canSuggestFix,
}: {
  clauseText: string; sectionLabel: string; result: ClauseRiskResult;
  positionLabel?: string;
  isEdited?: boolean;
  onUndoEdit?: () => void;
  onClose: () => void;
  onSuggestFix: () => void; onDismiss: () => void; suggestLoading: boolean;
  canSuggestFix: boolean | null;
}) {
  const color = riskColor(result.risk_level);
  const stripeBg = riskBg(result.risk_level);
  const sortedFactors = Object.entries(result.factors).sort(([, a], [, b]) => b.score - a.score);

  return (
    <div className="h-full flex flex-col overflow-hidden bg-white">
      {/* Header */}
      <div className="shrink-0 px-5 pt-4 pb-3 border-b border-slate-200"
        style={{ background: stripeBg, borderLeft: `4px solid ${color}` }}>
        <div className="flex items-start justify-between mb-1 gap-3">
          {/* Left: risk label + position */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="text-[10px] font-bold tracking-widest uppercase" style={{ color }}>
                RISK · {result.risk_level.toUpperCase()}
              </div>
              {isEdited && onUndoEdit && (
                <button
                  onClick={onUndoEdit}
                  className="text-[10px] font-medium underline decoration-dotted text-slate-500 hover:text-slate-800 transition-colors"
                  title="Restore the original seeded clause text"
                >
                  ↶ Undo edit
                </button>
              )}
            </div>
            {positionLabel && (
              <div className="text-[11px] text-slate-500 mt-0.5">{positionLabel}</div>
            )}
          </div>

          {/* Right: score badge + close X — in-flow, no absolute positioning */}
          <div className="flex items-center gap-2 shrink-0">
            <div
              className="flex items-baseline gap-0.5 px-2.5 py-1 rounded-lg"
              style={{ background: riskBg(result.risk_level) }}
            >
              <span className="text-xl font-bold tabular-nums leading-none" style={{ color }}>
                {result.score}
              </span>
              <span className="text-[11px] font-medium text-slate-400 leading-none">/100</span>
            </div>
            <button
              onClick={onClose}
              className="w-6 h-6 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors"
              aria-label="Close panel"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-600 leading-snug mt-1">{result.summary}</p>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <section>
          <p className="text-[10px] font-bold tracking-widest text-slate-400 uppercase mb-1.5">Clause</p>
          <blockquote className="border-l-2 border-slate-200 pl-3 text-sm text-slate-700 leading-relaxed italic">
            {clauseText}
          </blockquote>
          {sectionLabel && <p className="text-[10px] text-slate-400 mt-1 pl-3">{sectionLabel}</p>}
        </section>

        <div className="border-t border-slate-100" />

        <section>
          <p className="text-[10px] font-bold tracking-widest text-slate-400 uppercase mb-3">Why this clause is risky</p>
          <div className="space-y-3.5">
            {sortedFactors.map(([key, factor]) => {
              const fc = barColor(factor.score);
              return (
                <div key={key}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-slate-700">
                      {FACTOR_LABELS[key] ?? key}
                    </span>
                    <span className="text-xs font-bold tabular-nums" style={{ color: fc }}>
                      {factor.score}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <motion.div className="h-full rounded-full" style={{ background: fc }}
                      initial={{ width: 0 }}
                      animate={{ width: `${factor.score}%` }}
                      transition={{ duration: 0.35, ease: "easeOut", delay: 0.05 }} />
                  </div>
                  {factor.reasoning && (
                    <p className="text-[11px] text-slate-500 mt-1 leading-snug">{factor.reasoning}</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {result.top_pattern_match && (
          <>
            <div className="border-t border-slate-100" />
            <section>
              <p className="text-[10px] font-bold tracking-widest text-slate-400 uppercase mb-2">
                Matched Amendment Pattern
              </p>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono text-xs font-semibold text-slate-700">
                    {result.top_pattern_match.pattern_id}
                  </span>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
                    style={{ background: riskBg(result.risk_level), color }}>
                    {result.top_pattern_match.match_percent}% match
                  </span>
                </div>
                <p className="text-xs text-slate-700 leading-snug">{result.top_pattern_match.description}</p>
                <p className="text-[10px] text-slate-400 mt-2">
                  Source: Synthetic, modeled on Tufts CSDD amendment categories
                </p>
              </div>
            </section>
          </>
        )}
      </div>

      {/* Actions */}
      <div className="shrink-0 px-5 py-3 border-t border-slate-200 flex items-center justify-between gap-2 bg-white">
        {canSuggestFix === false ? (
          <span className="text-[11px] italic text-slate-500 leading-snug">
            This is a custom clause. Edit manually to reduce risk.
          </span>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-2">
          <button onClick={onDismiss}
            className="px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-300 rounded-md hover:bg-slate-50 transition-colors">
            Dismiss
          </button>
          {canSuggestFix !== false && (
            <button onClick={onSuggestFix} disabled={suggestLoading || canSuggestFix === null}
              className="px-3 py-1.5 text-xs font-semibold text-white rounded-md transition-colors disabled:opacity-60"
              style={{ background: "#14b8a6" }}
              onMouseEnter={(e) => { if (!suggestLoading) e.currentTarget.style.background = "#0d9488"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "#14b8a6"; }}>
              {suggestLoading ? "Analyzing…" : canSuggestFix === null ? "Checking…" : "Suggest Fix →"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function CandidateCard({
  candidate, isRecommended, isAccepting, onAccept,
}: {
  candidate: FixCandidate; isRecommended: boolean;
  isAccepting: boolean; onAccept: () => void;
}) {
  const [showCompare, setShowCompare] = useState(false);
  const acceptBtnRef = useRef<HTMLButtonElement>(null);
  const deltaColor = candidate.delta_overall <= -15 ? "#16a34a" : candidate.delta_overall <= -8 ? "#d97706" : "#6b7280";

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-800">{candidate.label}</span>
          {isRecommended && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-teal-100 text-teal-700 tracking-wide">
              RECOMMENDED
            </span>
          )}
        </div>
        <span className="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full"
          style={{ background: "rgba(22,163,74,0.10)", color: deltaColor }}>
          {candidate.delta_overall}% overall risk
        </span>
      </div>

      {/* New text preview */}
      <blockquote className="border-l-2 border-teal-300 pl-3 text-xs text-slate-700 leading-relaxed italic">
        {candidate.new_text}
      </blockquote>

      {/* Compare toggle */}
      <button
        onClick={() => setShowCompare((v) => !v)}
        className="text-[10px] text-slate-400 hover:text-slate-600 transition-colors"
      >
        {showCompare ? "▲ Hide comparison" : "▼ Compare with original"}
      </button>

      <AnimatePresence>
        {showCompare && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-1 pt-1">
              <p className="text-[10px] text-slate-400 uppercase tracking-wide mb-1">Original</p>
              <p className="text-xs text-slate-400 line-through leading-relaxed pl-2">
                {/* Shown from parent's original field */}
                (see clause text above)
              </p>
              <p className="text-[10px] text-slate-400 uppercase tracking-wide mt-2 mb-1">Proposed</p>
              <p className="text-xs text-slate-700 leading-relaxed pl-2">{candidate.new_text}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Rationale */}
      <p className="text-[11px] text-slate-500 leading-snug">{candidate.rationale}</p>

      {/* Accept */}
      <div className="flex justify-end">
        <button
          ref={acceptBtnRef}
          onClick={() => {
            _lastAcceptButtonRect = acceptBtnRef.current?.getBoundingClientRect() ?? null;
            onAccept();
          }}
          disabled={isAccepting}
          className="px-3 py-1.5 text-xs font-semibold text-white rounded-md disabled:opacity-60 transition-colors"
          style={{ background: "#14b8a6" }}
          onMouseEnter={(e) => { if (!isAccepting) e.currentTarget.style.background = "#0d9488"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "#14b8a6"; }}
        >
          {isAccepting ? "Applying…" : "Accept this fix"}
        </button>
      </div>
    </div>
  );
}

function CandidatesView({
  candidates, acceptingId, onAccept, onBack, onClose,
}: {
  candidates: FixCandidate[]; acceptingId: string | null;
  onAccept: (c: FixCandidate) => void; onBack: () => void; onClose: () => void;
}) {
  return (
    <div className="h-full flex flex-col overflow-hidden bg-slate-50">
      <div className="shrink-0 px-5 pt-4 pb-3 border-b border-slate-200 bg-white flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-xs text-slate-500 hover:text-slate-800 transition-colors">
            ← Back
          </button>
          <span className="text-xs font-semibold text-slate-700">Choose a fix</span>
        </div>
        <button
          onClick={onClose}
          className="w-6 h-6 rounded-full flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors"
          aria-label="Close panel"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {candidates.map((c, i) => (
          <CandidateCard
            key={c.candidate_id}
            candidate={c}
            isRecommended={i === 0}
            isAccepting={acceptingId === c.candidate_id}
            onAccept={() => onAccept(c)}
          />
        ))}
      </div>
    </div>
  );
}

function SuccessView({ onNextIssue }: { onNextIssue: (() => void) | null }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 bg-white px-8 text-center">
      <div className="w-14 h-14 rounded-full flex items-center justify-center"
        style={{ background: "rgba(22,163,74,0.12)" }}>
        <svg className="w-7 h-7" style={{ color: "#16a34a" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <div>
        <p className="text-sm font-semibold text-slate-800">Fixed ✓</p>
        <p className="text-xs text-slate-500 mt-1">Clause revised. Amendment risk updated.</p>
      </div>
      {onNextIssue && (
        <button
          onClick={onNextIssue}
          className="mt-2 px-4 py-2 text-xs font-semibold text-white rounded-md transition-colors"
          style={{ background: "#14b8a6" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#0d9488")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "#14b8a6")}
        >
          Next issue →
        </button>
      )}
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

type PanelView = "analysis" | "candidates" | "success";

export default function IssuePanel({
  blockId, clauseText, sectionLabel, result, positionLabel,
  isEdited, onClose, onAccept, onDismiss, onUndoEdit, onNextIssue,
}: Props) {
  const [view, setView] = useState<PanelView>("analysis");
  const [candidates, setCandidates] = useState<FixCandidate[]>([]);
  const [acceptingId, setAcceptingId] = useState<string | null>(null);
  // suggestLoading: true while probing, drives the "Checking…" button label
  const suggestLoading = false;
  // null = probing, true/false = known. Probe runs on mount/clause change.
  const [canSuggestFix, setCanSuggestFix] = useState<boolean | null>(null);

  // Probe whether fix candidates exist for this clause (without showing the candidates view yet)
  useEffect(() => {
    let cancelled = false;
    setCanSuggestFix(null);
    setCandidates([]);
    setView("analysis");
    apiSuggestFix("DIABETES-2026-PH3", blockId, clauseText)
      .then((resp) => {
        if (cancelled) return;
        setCandidates(resp.candidates);
        setCanSuggestFix(resp.candidates.length > 0);
      })
      .catch((e) => {
        if (cancelled) return;
        console.error("Suggest fix probe failed:", e);
        setCanSuggestFix(false);
      });
    return () => { cancelled = true; };
  }, [blockId, clauseText]);

  const handleSuggestFix = () => {
    // Candidates already loaded from the probe; just switch view
    if (candidates.length > 0) setView("candidates");
  };

  const handleAccept = async (candidate: FixCandidate) => {
    setAcceptingId(candidate.candidate_id);
    try {
      await onAccept(candidate);
      setView("success");
    } catch (e) {
      console.error("Accept failed:", e);
    } finally {
      setAcceptingId(null);
    }
  };

  const handleDismiss = async () => {
    onDismiss();
    onClose();
  };

  return (
    <div className="h-full relative flex flex-col">
      <AnimatePresence mode="wait">
        {view === "analysis" && (
          <motion.div key="analysis" className="absolute inset-0"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}>
            <AnalysisView
              clauseText={clauseText} sectionLabel={sectionLabel} result={result}
              positionLabel={positionLabel}
              isEdited={isEdited}
              onUndoEdit={onUndoEdit}
              onClose={onClose}
              onSuggestFix={handleSuggestFix} onDismiss={handleDismiss}
              suggestLoading={suggestLoading}
              canSuggestFix={canSuggestFix}
            />
          </motion.div>
        )}

        {view === "candidates" && (
          <motion.div key="candidates" className="absolute inset-0"
            initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}>
            <CandidatesView
              candidates={candidates} acceptingId={acceptingId}
              onAccept={handleAccept}
              onBack={() => setView("analysis")}
              onClose={onClose} />
          </motion.div>
        )}

        {view === "success" && (
          <motion.div key="success" className="absolute inset-0"
            initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
            <SuccessView onNextIssue={onNextIssue ?? null} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Export a function to allow EditorPage to set the "next issue" callback
export type { PanelView };
