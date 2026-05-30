import { useState, useEffect, useCallback, useRef } from "react";
import {
  scoreProtocol,
  resetProtocol,
  type ClauseRiskResult,
  type SeverityCounts,
} from "@/lib/api";

export interface ProtocolScoreState {
  clauseScores: Map<string, ClauseRiskResult>;
  overallRisk: number;
  severityCounts: SeverityCounts;
  loading: boolean;
  error: string | null;
  updateClauseScore: (blockId: string, result: ClauseRiskResult) => void;
  setOverallRisk: (risk: number) => void;
  setSeverityCounts: (counts: SeverityCounts) => void;
  // Phase 5 live-edit additions:
  mergeClauseScores: (updates: ClauseRiskResult[]) => void;
  removeClauseScores: (blockIds: string[]) => void;
  // Recompute-from-map variants. These derive overall + severity from the
  // CLIENT's score map (which reflects client-only edits/deletions the backend
  // doesn't know about), so a live re-score of one clause can't reset counts
  // that a sibling deletion already lowered.
  mergeClauseScoresAndRecompute: (updates: ClauseRiskResult[]) => void;
  removeClauseScoresAndRecompute: (blockIds: string[]) => void;
}

const EMPTY_COUNTS: SeverityCounts = { high: 0, medium: 0, low: 0 };

// The locked aggregation formula (mirrors backend compute_overall_risk).
function aggregatesFromMap(map: Map<string, ClauseRiskResult>): {
  overall: number;
  counts: SeverityCounts;
} {
  let high = 0, medium = 0, low = 0;
  map.forEach((r) => {
    if (r.risk_level === "high") high++;
    else if (r.risk_level === "medium") medium++;
    else low++;
  });
  return {
    overall: Math.round(high * 18 + medium * 3 + low / 3),
    counts: { high, medium, low },
  };
}

export function useProtocolScore(protocolId: string): ProtocolScoreState {
  const [clauseScores, setClauseScores] = useState<Map<string, ClauseRiskResult>>(
    new Map()
  );
  const [overallRisk, setOverallRisk] = useState(0);
  const [severityCounts, setSeverityCounts] = useState<SeverityCounts>(EMPTY_COUNTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Synchronous mirror of clauseScores so recompute-from-map mutators can read
  // the latest map without waiting for a React render.
  const mapRef = useRef<Map<string, ClauseRiskResult>>(new Map());
  const commitMap = useCallback((next: Map<string, ClauseRiskResult>) => {
    mapRef.current = next;
    setClauseScores(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Reset persistent state from any prior session so each load shows the demo baseline
    resetProtocol(protocolId)
      .then(() => scoreProtocol(protocolId))
      .then((resp) => {
        if (cancelled) return;
        const map = new Map<string, ClauseRiskResult>();
        resp.clauses.forEach((c) => map.set(c.block_id, c));
        commitMap(map);
        setOverallRisk(resp.overall_risk);
        setSeverityCounts(resp.severity_counts);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [protocolId, commitMap]);

  const updateClauseScore = useCallback((blockId: string, result: ClauseRiskResult) => {
    const next = new Map(mapRef.current);
    next.set(blockId, result);
    commitMap(next);
  }, [commitMap]);

  const mergeClauseScores = useCallback((updates: ClauseRiskResult[]) => {
    if (updates.length === 0) return;
    const next = new Map(mapRef.current);
    updates.forEach((r) => next.set(r.block_id, r));
    commitMap(next);
  }, [commitMap]);

  const removeClauseScores = useCallback((blockIds: string[]) => {
    if (blockIds.length === 0) return;
    const next = new Map(mapRef.current);
    blockIds.forEach((id) => next.delete(id));
    commitMap(next);
  }, [commitMap]);

  const mergeClauseScoresAndRecompute = useCallback((updates: ClauseRiskResult[]) => {
    if (updates.length === 0) return;
    const next = new Map(mapRef.current);
    updates.forEach((r) => next.set(r.block_id, r));
    commitMap(next);
    const { overall, counts } = aggregatesFromMap(next);
    setOverallRisk(overall);
    setSeverityCounts(counts);
  }, [commitMap]);

  const removeClauseScoresAndRecompute = useCallback((blockIds: string[]) => {
    if (blockIds.length === 0) return;
    const next = new Map(mapRef.current);
    blockIds.forEach((id) => next.delete(id));
    commitMap(next);
    const { overall, counts } = aggregatesFromMap(next);
    setOverallRisk(overall);
    setSeverityCounts(counts);
  }, [commitMap]);

  return {
    clauseScores,
    overallRisk,
    severityCounts,
    loading,
    error,
    updateClauseScore,
    setOverallRisk,
    setSeverityCounts,
    mergeClauseScores,
    removeClauseScores,
    mergeClauseScoresAndRecompute,
    removeClauseScoresAndRecompute,
  };
}
