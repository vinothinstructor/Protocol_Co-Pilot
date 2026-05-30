import { create } from "zustand";

export interface FeasibilityMetric {
  name: string;
  current_value: number;
  baseline_value: number;
  unit: string;
  delta: number;
  delta_label: string;
}

export interface FeasibilityProjection {
  protocol_id: string;
  protocol_version: string;
  overall_risk: number;
  overall_risk_baseline: number;
  metrics: FeasibilityMetric[];
  rationale: string;
  generated_at: string;
}

interface FeasibilityState {
  currentProjection: FeasibilityProjection | null;
  baselineProjection: FeasibilityProjection | null;
  panelOpen: boolean;
  lastToastDelta: FeasibilityProjection | null;
  feasibilityError: string | null;
  setProjection: (proj: FeasibilityProjection) => void;
  clearProjection: () => void;
  setBaseline: (proj: FeasibilityProjection) => void;
  setPanelOpen: (open: boolean) => void;
  setLastToastDelta: (delta: FeasibilityProjection | null) => void;
  setFeasibilityError: (error: string | null) => void;
}

export const useFeasibilityStore = create<FeasibilityState>((set) => ({
  currentProjection: null,
  baselineProjection: null,
  panelOpen: false,
  lastToastDelta: null,
  feasibilityError: null,
  setProjection: (proj) => set({ currentProjection: proj, feasibilityError: null }),
  clearProjection: () => set({ currentProjection: null }),
  setBaseline: (proj) => set({ baselineProjection: proj }),
  setPanelOpen: (open) => set({ panelOpen: open }),
  setLastToastDelta: (delta) => set({ lastToastDelta: delta }),
  setFeasibilityError: (error) => set({ feasibilityError: error }),
}));

/** Build a "delta" projection showing step-wise change (from → to). */
export function buildToastDelta(
  from: FeasibilityProjection,
  to: FeasibilityProjection
): FeasibilityProjection {
  const metrics = to.metrics.map((toMetric) => {
    const fromMetric = from.metrics.find((m) => m.name === toMetric.name);
    const fromVal = fromMetric?.current_value ?? toMetric.baseline_value;
    const delta = toMetric.current_value - fromVal;

    let delta_label = "no change";
    if (delta !== 0) {
      if (toMetric.name === "screen_failure_rate") delta_label = `${delta > 0 ? "+" : ""}${delta.toFixed(0)} pts`;
      else if (toMetric.name === "sites_required") delta_label = `${delta > 0 ? "+" : ""}${delta.toFixed(0)} sites`;
      else if (toMetric.name === "time_to_lsi_weeks") delta_label = `${delta > 0 ? "+" : ""}${delta.toFixed(0)} wk`;
      else if (toMetric.name === "enrollment_cost_savings_usd_m") delta_label = `+$${toMetric.current_value.toFixed(1)}M saved`;
    }

    return {
      ...toMetric,
      baseline_value: fromVal,
      delta,
      delta_label,
    };
  });

  return { ...to, metrics };
}
