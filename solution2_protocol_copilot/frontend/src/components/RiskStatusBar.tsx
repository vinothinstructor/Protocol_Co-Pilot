import { useEffect, useRef, useState } from "react";
import { AnimatePresence, animate, motion } from "framer-motion";
import { FileDown, Activity, AlertCircle } from "lucide-react";
import type { SeverityCounts } from "@/lib/api";
import { useFeasibilityStore } from "@/stores/feasibilityStore";
import { useDraftingStore } from "@/stores/draftingStore";

interface Props {
  overallRisk: number;
  severityCounts: SeverityCounts;
  loading: boolean;
  /** How many fixes have been accepted in this session (drives Export visibility). */
  acceptedFixesCount?: number;
  /** Called when the user clicks "Export amendment package". */
  onExportClick?: () => void;
}

function riskColor(score: number): string {
  if (score >= 60) return "#dc2626";
  if (score >= 30) return "#d97706";
  return "#16a34a";
}

function riskBg(score: number): string {
  if (score >= 60) return "rgba(220,38,38,0.06)";
  if (score >= 30) return "rgba(217,119,6,0.06)";
  return "rgba(22,163,74,0.06)";
}

export default function RiskStatusBar({
  overallRisk, severityCounts, loading, acceptedFixesCount = 0, onExportClick,
}: Props) {
  const { panelOpen, setPanelOpen } = useFeasibilityStore();
  const { gapsDetected, gapPanelOpen, setGapPanelOpen, gapsLoading } = useDraftingStore();
  const { setPanelOpen: setFeasibilityPanelOpen } = useFeasibilityStore();

  const handleGapChipClick = () => {
    // Mutual exclusion: opening gap panel closes feasibility panel
    setFeasibilityPanelOpen(false);
    setGapPanelOpen(!gapPanelOpen);
  };
  // Animated display value — tweens from old to new on every overallRisk change
  const [displayRisk, setDisplayRisk] = useState(overallRisk);
  const prevRiskRef = useRef(overallRisk);

  useEffect(() => {
    const from = prevRiskRef.current;
    const to = overallRisk;
    prevRiskRef.current = to;
    if (from === to) return;

    const controls = animate(from, to, {
      duration: 0.85,
      ease: "easeInOut",
      onUpdate: (v) => setDisplayRisk(Math.round(v)),
    });
    return () => controls.stop();
  }, [overallRisk]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 px-6 py-2 bg-slate-100 border-b border-slate-200 shrink-0">
        <span className="text-xs text-slate-400 italic animate-pulse">
          Analyzing protocol…
        </span>
      </div>
    );
  }

  const color = riskColor(displayRisk);
  const bg = riskBg(displayRisk);

  // Phase 7 — Export button visible when ALL HIGH-risk clauses are resolved
  // AND at least one fix has been accepted in this session. acceptedFixesCount
  // is tracked client-side because the protocol version no longer bumps on
  // each Accept Fix (version bumps once per amendment-package generation).
  const showExport =
    severityCounts.high === 0 && acceptedFixesCount >= 1 && !!onExportClick;

  return (
    <div
      className="flex items-center gap-6 px-6 py-2 border-b border-slate-200 shrink-0 transition-colors duration-700"
      style={{ backgroundColor: bg }}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-500 tracking-widest uppercase">
          Amendment Risk:
        </span>
        <span
          data-risk-score
          className="text-sm font-bold tabular-nums transition-colors duration-700"
          style={{ color }}
        >
          {displayRisk}%
        </span>
      </div>

      <div className="w-px h-4 bg-slate-300" />

      <div className="flex items-center gap-4 text-xs">
        <span className="flex items-center gap-1.5 font-medium" style={{ color: "#dc2626" }}>
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: "#dc2626" }} />
          {severityCounts.high} HIGH
        </span>
        <span className="flex items-center gap-1.5 font-medium" style={{ color: "#d97706" }}>
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: "#d97706" }} />
          {severityCounts.medium} MED
        </span>
        <span className="flex items-center gap-1.5 font-medium" style={{ color: "#64748b" }}>
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: "#64748b" }} />
          {severityCounts.low} LOW
        </span>
      </div>

      {/* Gap Detection chip — shows when gaps > 0 or loading */}
      <AnimatePresence>
        {(gapsDetected.length > 0 || gapsLoading) && (
          <motion.div
            key="gap-chip"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.25 }}
            className="flex items-center gap-6"
          >
            <div className="w-px h-4 bg-slate-300" />
            <button
              onClick={handleGapChipClick}
              disabled={gapsLoading}
              title="View protocol gaps detected by the Drafting Agent"
              aria-label="Protocol gaps detected"
              className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold transition-colors disabled:opacity-60"
              style={{
                background: gapPanelOpen ? "rgba(217,119,6,0.15)" : "rgba(217,119,6,0.08)",
                color: "#d97706",
                border: `1px solid rgba(217,119,6,${gapPanelOpen ? "0.4" : "0.2"})`,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(217,119,6,0.15)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = gapPanelOpen ? "rgba(217,119,6,0.15)" : "rgba(217,119,6,0.08)";
              }}
            >
              <AlertCircle size={13} strokeWidth={2.25} />
              {gapsLoading
                ? "Checking gaps…"
                : `${gapsDetected.length} protocol gap${gapsDetected.length !== 1 ? "s" : ""} detected`}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Feasibility Simulator button */}
      <div className="w-px h-4 bg-slate-300" />
      <button
        onClick={() => { setPanelOpen(!panelOpen); setGapPanelOpen(false); }}
        title="Feasibility outlook"
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors"
        style={{
          color: "#0d9488",
          background: panelOpen ? "rgba(13,148,136,0.12)" : "rgba(13,148,136,0.06)",
          border: `1px solid rgba(13,148,136,${panelOpen ? "0.35" : "0.18"})`,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "rgba(13,148,136,0.14)";
          e.currentTarget.style.borderColor = "rgba(13,148,136,0.4)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = panelOpen ? "rgba(13,148,136,0.12)" : "rgba(13,148,136,0.06)";
          e.currentTarget.style.borderColor = `rgba(13,148,136,${panelOpen ? "0.35" : "0.18"})`;
        }}
        aria-label="Feasibility outlook"
      >
        <Activity size={14} strokeWidth={2.25} />
        <span>Feasibility</span>
      </button>

      {/* Phase 7 Export button — fades + scales in when all HIGH are resolved */}
      <div className="ml-auto">
        <AnimatePresence>
          {showExport && (
            <motion.button
              key="export-btn"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              onClick={onExportClick}
              className="flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold text-white transition-colors"
              style={{ background: "#0d9488" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#0f766e")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#0d9488")}
            >
              <FileDown size={14} strokeWidth={2.25} />
              Export amendment package
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
