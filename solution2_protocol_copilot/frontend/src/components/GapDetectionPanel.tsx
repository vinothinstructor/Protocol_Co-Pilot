import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, CheckCircle2, Loader2, BookOpen } from "lucide-react";
import { useDraftingStore, type ProtocolGap } from "@/stores/draftingStore";
import { useFeasibilityStore } from "@/stores/feasibilityStore";
import { draftClause } from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  exclusion_criteria: "Exclusion Criteria",
  inclusion_criteria: "Inclusion Criteria",
  safety_reporting: "Safety Reporting",
  visit_schedule: "Visit Schedule",
  other: "General",
  mock: "Mock",
};

const CATEGORY_COLORS: Record<string, { bg: string; text: string }> = {
  exclusion_criteria: { bg: "rgba(220,38,38,0.08)", text: "#dc2626" },
  inclusion_criteria: { bg: "rgba(22,163,74,0.08)", text: "#16a34a" },
  safety_reporting: { bg: "rgba(217,119,6,0.08)", text: "#d97706" },
  visit_schedule: { bg: "rgba(37,99,235,0.08)", text: "#2563eb" },
  other: { bg: "rgba(100,116,139,0.08)", text: "#64748b" },
  mock: { bg: "rgba(100,116,139,0.08)", text: "#64748b" },
};

interface GapCardProps {
  gap: ProtocolGap;
  protocolId: string;
  onDrafted: (gapId: string) => void;
  onInsertClause: (sectionId: string, clauseText: string) => void;
}

function GapCard({ gap, protocolId, onDrafted, onInsertClause }: GapCardProps) {
  const [state, setState] = useState<"idle" | "drafting" | "drafted">("idle");
  const { setFeasibilityError } = useFeasibilityStore();
  const catColor = CATEGORY_COLORS[gap.category] ?? CATEGORY_COLORS.other;
  const catLabel = CATEGORY_LABELS[gap.category] ?? gap.category;

  const handleDraft = async () => {
    if (state !== "idle") return;
    setState("drafting");
    try {
      const resp = await draftClause(protocolId, gap.draft_topic, gap.suggested_section_id);
      onInsertClause(gap.suggested_section_id, resp.clause_text);
      setState("drafted");
      // Fade card out and remove from list after delay
      setTimeout(() => onDrafted(gap.gap_id), 1800);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Drafting failed.";
      setFeasibilityError(msg);
      setState("idle");
    }
  };

  return (
    <motion.div
      layout
      exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: "hidden" }}
      transition={{ duration: 0.35, ease: "easeInOut" }}
      className="rounded-lg border border-slate-100 bg-white p-4 mb-3 last:mb-0"
    >
      {state === "drafted" ? (
        <div className="flex items-center gap-2 py-2">
          <CheckCircle2 size={16} style={{ color: "#16a34a" }} />
          <span className="text-sm font-medium" style={{ color: "#16a34a" }}>
            Drafted ✓ — clause inserted and scored
          </span>
        </div>
      ) : (
        <>
          {/* Header row */}
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1 min-w-0">
              <span
                className="inline-block text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded mb-1.5"
                style={{ background: catColor.bg, color: catColor.text }}
              >
                {catLabel}
              </span>
              <p className="text-sm font-bold leading-snug" style={{ color: "#1a2744" }}>
                {gap.name}
              </p>
            </div>
            <button
              onClick={handleDraft}
              disabled={state !== "idle"}
              className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-md text-white shrink-0 transition-colors disabled:opacity-50"
              style={{ background: "#0d9488" }}
              onMouseEnter={(e) => {
                if (state === "idle") e.currentTarget.style.background = "#0f766e";
              }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "#0d9488"; }}
            >
              {state === "drafting" ? (
                <>
                  <Loader2 size={12} className="animate-spin" />
                  Drafting…
                </>
              ) : (
                "Draft this clause"
              )}
            </button>
          </div>

          {/* Suggested section */}
          <p className="text-[11px] text-slate-400 mb-1.5">
            Suggested for: {gap.suggested_section}
          </p>

          {/* Rationale */}
          <p className="text-xs text-slate-600 leading-relaxed mb-2">
            {gap.rationale}
          </p>

          {/* Regulatory reference */}
          {gap.regulatory_reference && (
            <p className="text-[10px] text-slate-400 italic">
              {gap.regulatory_reference}
            </p>
          )}
        </>
      )}
    </motion.div>
  );
}

interface Props {
  protocolId: string;
  onInsertClause: (sectionId: string, clauseText: string) => void;
}

export default function GapDetectionPanel({ protocolId, onInsertClause }: Props) {
  const { gapsDetected, gapPanelOpen, setGapPanelOpen, removeGap } = useDraftingStore();
  const { setPanelOpen: setFeasibilityPanelOpen } = useFeasibilityStore();

  const handleClose = () => setGapPanelOpen(false);

  // Opening gap panel closes feasibility panel
  const handleOpen = () => {
    setFeasibilityPanelOpen(false);
    setGapPanelOpen(true);
  };
  void handleOpen; // referenced from store action, not directly used here

  const handleDrafted = (gapId: string) => removeGap(gapId);

  return (
    <AnimatePresence>
      {gapPanelOpen && (
        <motion.div
          key="gap-panel"
          initial={{ opacity: 0, x: 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 32 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="absolute inset-0 bg-slate-50 flex flex-col overflow-hidden border-l border-slate-200 z-10"
        >
          {/* Header */}
          <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-slate-100 bg-white shrink-0">
            <div>
              <div className="flex items-center gap-2">
                <BookOpen size={14} style={{ color: "#d97706" }} strokeWidth={2.25} />
                <h2 className="text-sm font-bold text-slate-800">Protocol Gaps Detected</h2>
                {gapsDetected.length > 0 && (
                  <span
                    className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                    style={{ background: "rgba(217,119,6,0.1)", color: "#d97706" }}
                  >
                    {gapsDetected.length} gap{gapsDetected.length !== 1 ? "s" : ""} · ICH/FDA-aligned
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5 italic leading-snug">
                These clauses are expected in a complete Phase III diabetes protocol but appear to be missing.
              </p>
            </div>
            <button
              onClick={handleClose}
              className="text-slate-400 hover:text-slate-600 transition-colors mt-0.5"
              aria-label="Close gap panel"
            >
              <X size={16} />
            </button>
          </div>

          {/* Gap cards */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            {gapsDetected.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <CheckCircle2 size={32} className="mx-auto mb-3" style={{ color: "#16a34a" }} />
                  <p className="text-sm font-semibold text-slate-600">All gaps resolved</p>
                  <p className="text-xs text-slate-400 mt-1">
                    The Drafting Agent has addressed all detected gaps.
                  </p>
                </div>
              </div>
            ) : (
              <AnimatePresence initial={false}>
                {gapsDetected.map((gap) => (
                  <GapCard
                    key={gap.gap_id}
                    gap={gap}
                    protocolId={protocolId}
                    onDrafted={handleDrafted}
                    onInsertClause={onInsertClause}
                  />
                ))}
              </AnimatePresence>
            )}
          </div>

          {/* Footer */}
          <div className="px-5 py-2.5 border-t border-slate-100 bg-white shrink-0">
            <p className="text-[10px] text-slate-300 italic">
              Checklist v1.0 · Drafting Agent · grounded in ICH M3(R2), FDA Diabetes Guidance, ADA Standards of Care
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
