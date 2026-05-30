import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, X } from "lucide-react";
import { useFeasibilityStore } from "@/stores/feasibilityStore";

function MetricLine({ metric }: { metric: { name: string; baseline_value: number; current_value: number; delta_label: string; unit: string } }) {
  const isCost = metric.name === "enrollment_cost_savings_usd_m";
  const improved = isCost ? metric.current_value > metric.baseline_value : metric.current_value < metric.baseline_value;
  const unchanged = metric.current_value === metric.baseline_value;

  const label = metric.name === "screen_failure_rate"
    ? "Screen failure"
    : metric.name === "time_to_lsi_weeks"
    ? "Time to LSI"
    : metric.name === "sites_required"
    ? "Sites needed"
    : "Cost savings";

  const fromStr = isCost
    ? `$${metric.baseline_value.toFixed(1)}M`
    : `${metric.baseline_value}${metric.unit}`;
  const toStr = isCost
    ? `$${metric.current_value.toFixed(1)}M`
    : `${metric.current_value}${metric.unit}`;

  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-slate-500">{label}:</span>
      <div className="flex items-center gap-1.5">
        <span className="text-slate-700 tabular-nums">{fromStr}</span>
        <span className="text-slate-400">→</span>
        <span className="font-semibold tabular-nums" style={{ color: unchanged ? "#64748b" : improved ? "#0d9488" : "#dc2626" }}>
          {toStr}
        </span>
        {!unchanged && (
          <span
            className="px-1.5 py-0.5 rounded text-[10px] font-bold"
            style={{
              background: improved ? "rgba(13,148,136,0.12)" : "rgba(220,38,38,0.1)",
              color: improved ? "#0d9488" : "#dc2626",
            }}
          >
            {metric.delta_label}
          </span>
        )}
      </div>
    </div>
  );
}

export default function FeasibilityToast() {
  const { lastToastDelta, setLastToastDelta, setPanelOpen } = useFeasibilityStore();

  // Auto-dismiss after 5s
  useEffect(() => {
    if (!lastToastDelta) return;
    const id = setTimeout(() => setLastToastDelta(null), 5000);
    return () => clearTimeout(id);
  }, [lastToastDelta, setLastToastDelta]);

  const handleViewFull = () => {
    setLastToastDelta(null);
    setPanelOpen(true);
  };

  const isMock = lastToastDelta?.rationale?.includes("Mock mode");

  // Show only screen_failure_rate and time_to_lsi_weeks in the toast
  const toastMetrics = lastToastDelta?.metrics.filter((m) =>
    m.name === "screen_failure_rate" || m.name === "time_to_lsi_weeks"
  ) ?? [];

  return (
    <AnimatePresence>
      {lastToastDelta && (
        <motion.div
          key="feasibility-toast"
          initial={{ opacity: 0, y: 20, x: 0 }}
          animate={{ opacity: 1, y: 0, x: 0 }}
          exit={{ opacity: 0, y: 10 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className="fixed z-50 rounded-lg shadow-lg border border-slate-200 bg-white overflow-hidden"
          style={{ right: "1.5rem", bottom: "1.5rem", width: 340 }}
        >
          {/* Teal left accent */}
          <div className="absolute left-0 top-0 bottom-0 w-1 rounded-l-lg" style={{ background: "#0d9488" }} />

          <div className="pl-4 pr-3 pt-3 pb-3">
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <Activity size={13} style={{ color: "#0d9488" }} strokeWidth={2.25} />
                <span
                  className="text-[10px] font-bold tracking-widest uppercase"
                  style={{ color: "#0d9488" }}
                >
                  Feasibility Simulator
                </span>
              </div>
              <button
                onClick={() => setLastToastDelta(null)}
                className="text-slate-400 hover:text-slate-600 transition-colors"
                aria-label="Dismiss"
              >
                <X size={14} />
              </button>
            </div>

            {isMock ? (
              <p className="text-xs text-slate-400 italic">
                Feasibility data unavailable in mock mode.
              </p>
            ) : (
              <div className="space-y-1.5 mb-2.5">
                {toastMetrics.map((m) => (
                  <MetricLine key={m.name} metric={m} />
                ))}
              </div>
            )}

            {!isMock && (
              <button
                onClick={handleViewFull}
                className="text-[11px] font-medium mt-1 transition-colors"
                style={{ color: "#0d9488" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#0f766e")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#0d9488")}
              >
                View full projection →
              </button>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
