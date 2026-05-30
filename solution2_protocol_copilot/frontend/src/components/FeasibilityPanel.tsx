import { AnimatePresence, motion } from "framer-motion";
import { X, AlertTriangle } from "lucide-react";
import { useFeasibilityStore, type FeasibilityProjection, type FeasibilityMetric } from "@/stores/feasibilityStore";
import { useModeStore } from "@/stores/modeStore";

const METRIC_LABELS: Record<string, { label: string; lowerIsBetter: boolean }> = {
  screen_failure_rate:           { label: "Screen failure rate", lowerIsBetter: true },
  sites_required:                { label: "Sites required",       lowerIsBetter: true },
  time_to_lsi_weeks:             { label: "Time to LSI",          lowerIsBetter: true },
  enrollment_cost_savings_usd_m: { label: "Cost savings",         lowerIsBetter: false },
};

const METRIC_ORDER = [
  "screen_failure_rate",
  "sites_required",
  "time_to_lsi_weeks",
  "enrollment_cost_savings_usd_m",
];

function formatValue(name: string, value: number, unit: string): string {
  if (name === "enrollment_cost_savings_usd_m") return `$${value.toFixed(1)}M`;
  if (unit === "%") return `${value}%`;
  if (unit === "weeks") return `${value} wk`;
  if (unit === "sites") return `${value}`;
  return `${value} ${unit}`;
}

interface MetricRowProps {
  metric: FeasibilityMetric;
  baselineMetric: FeasibilityMetric | undefined;
}

function MetricRow({ metric, baselineMetric }: MetricRowProps) {
  const config = METRIC_LABELS[metric.name];
  if (!config) return null;

  const baselineVal = baselineMetric?.current_value ?? metric.baseline_value;
  const currentVal = metric.current_value;
  const improved = config.lowerIsBetter ? currentVal < baselineVal : currentVal > baselineVal;
  const unchanged = currentVal === baselineVal;

  // Bar chart: normalize against baseline as 100%
  const barMax = config.lowerIsBetter
    ? Math.max(baselineVal, currentVal) * 1.05
    : Math.max(baselineVal, currentVal, 0.1) * 1.1;
  const baselinePct = Math.min(100, (baselineVal / barMax) * 100);
  const currentPct = Math.min(100, (currentVal / barMax) * 100);

  return (
    <div className="py-2.5 border-b border-slate-100 last:border-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-slate-600">{config.label}</span>
        <div className="flex items-center gap-3 text-xs tabular-nums">
          <span className="text-slate-400">{formatValue(metric.name, baselineVal, metric.unit)}</span>
          <span className="text-slate-300">→</span>
          <span
            className="font-semibold"
            style={{ color: unchanged ? "#64748b" : improved ? "#0d9488" : "#dc2626" }}
          >
            {formatValue(metric.name, currentVal, metric.unit)}
          </span>
          {!unchanged && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-bold ml-1"
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

      {/* Mini bar chart */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] text-slate-400 w-14 shrink-0">Baseline</span>
          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${baselinePct}%`, background: "#94a3b8" }}
            />
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] text-slate-400 w-14 shrink-0">Current</span>
          <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${currentPct}%`,
                background: unchanged ? "#94a3b8" : improved ? "#0d9488" : "#dc2626",
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function FeasibilityPanel() {
  const { panelOpen, setPanelOpen, currentProjection, baselineProjection, feasibilityError } = useFeasibilityStore();
  const selectedMode = useModeStore((s) => s.selectedMode);

  const proj = currentProjection;
  const baseline = baselineProjection;
  const isMock = proj?.rationale?.includes("Mock mode");
  const isError = !proj && !!feasibilityError;

  const metricByName = (p: FeasibilityProjection | null, name: string) =>
    p?.metrics.find((m) => m.name === name);

  return (
    <AnimatePresence>
      {panelOpen && (
        <motion.div
          key="feasibility-panel"
          initial={{ opacity: 0, x: 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 32 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="absolute inset-0 bg-white flex flex-col overflow-hidden border-l border-slate-200 z-10"
        >
          {/* Header */}
          <div className="flex items-start justify-between px-5 pt-4 pb-3 border-b border-slate-100 shrink-0">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-800">Feasibility Outlook</h2>
                {proj && (
                  <span
                    className="text-[10px] font-semibold px-1.5 py-0.5 rounded"
                    style={{ background: "rgba(13,148,136,0.1)", color: "#0d9488" }}
                  >
                    {proj.protocol_version}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Operational projections based on current protocol state
              </p>
            </div>
            <button
              onClick={() => setPanelOpen(false)}
              className="text-slate-400 hover:text-slate-600 transition-colors mt-0.5"
              aria-label="Close feasibility panel"
            >
              <X size={16} />
            </button>
          </div>

          {/* Column headers */}
          {!isMock && proj && (
            <div className="flex items-center px-5 py-2 border-b border-slate-100 shrink-0">
              <div className="w-1/3" />
              <div className="w-1/3 text-center">
                <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                  v3.2 Baseline
                </span>
              </div>
              <div className="w-1/3 text-right">
                <span
                  className="text-[10px] font-semibold uppercase tracking-wider"
                  style={{ color: "#0d9488" }}
                >
                  Current ({proj.protocol_version})
                </span>
              </div>
            </div>
          )}

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-5 py-1">
            {isError ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center max-w-xs">
                  <AlertTriangle
                    size={28}
                    strokeWidth={1.75}
                    className="mx-auto mb-3"
                    style={{ color: "#dc2626" }}
                  />
                  <p className="text-sm font-semibold text-slate-700 mb-1">
                    Feasibility data unavailable
                    {selectedMode === "live" ? " in live mode" : ""}
                  </p>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {feasibilityError}
                  </p>
                </div>
              </div>
            ) : isMock || !proj ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <p className="text-sm text-slate-400 italic">
                    {isMock
                      ? "Feasibility data unavailable in mock mode."
                      : "Loading feasibility projections…"}
                  </p>
                  <p className="text-xs text-slate-300 mt-1">
                    {isMock ? "Switch to FAKE, CACHED, or LIVE mode to see projections." : ""}
                  </p>
                </div>
              </div>
            ) : (
              <div className="pt-1">
                {METRIC_ORDER.map((name) => {
                  const currentMetric = metricByName(proj, name);
                  if (!currentMetric) return null;
                  const baselineM = metricByName(baseline, name);
                  return (
                    <MetricRow
                      key={name}
                      metric={currentMetric}
                      baselineMetric={baselineM}
                    />
                  );
                })}
              </div>
            )}
          </div>

          {/* Rationale footer */}
          {!isMock && proj?.rationale && (
            <div className="px-5 py-3 border-t border-slate-100 bg-slate-50 shrink-0">
              <p className="text-[11px] text-slate-400 italic leading-relaxed">
                {proj.rationale}
              </p>
              <p className="text-[10px] text-slate-300 mt-1.5">
                Projections generated by Feasibility Simulator Agent · grounded in matched amendment patterns
              </p>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
