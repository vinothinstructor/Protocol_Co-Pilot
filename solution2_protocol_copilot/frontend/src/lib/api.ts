import { useModeStore } from "@/stores/modeStore";

const BASE = "/api";

/**
 * Centralized fetch wrapper that attaches the X-LLM-Mode header from the
 * mode store on every request. The backend resolves the effective mode per
 * request from this header (falling back to its env-var default if absent).
 */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const mode = useModeStore.getState().selectedMode;
  const headers = new Headers(init.headers);
  headers.set("X-LLM-Mode", mode);
  return fetch(path, { ...init, headers });
}

// ── Protocol types ─────────────────────────────────────────────────────────────

export interface ProtocolBlock {
  block_id: string;
  type: "paragraph" | "clause";
  text: string;
}

export interface ProtocolSection {
  section_id: string;
  number: string;
  heading: string;
  blocks: ProtocolBlock[];
}

export interface Protocol {
  protocol_id: string;
  title: string;
  version: string;
  therapeutic_area: string;
  target_countries: string[];
  sections: ProtocolSection[];
}

export interface ProtocolResponse {
  protocol_id: string;
  version: string;
  document: Protocol;
}

export async function fetchProtocol(protocolId: string): Promise<ProtocolResponse> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}`);
  if (!res.ok) throw new Error(`Failed to fetch protocol: ${res.status} ${res.statusText}`);
  return res.json() as Promise<ProtocolResponse>;
}

// ── Score types ────────────────────────────────────────────────────────────────

export interface FactorScore {
  score: number;
  reasoning: string;
}

export interface PatternMatch {
  pattern_id: string;
  match_percent: number;
  description: string;
}

export interface ClauseRiskResult {
  block_id: string;
  score: number;
  risk_level: "low" | "medium" | "high";
  factors: Record<string, FactorScore>;
  top_pattern_match: PatternMatch | null;
  summary: string;
}

export interface SeverityCounts {
  high: number;
  medium: number;
  low: number;
}

export interface ScoreResponse {
  clauses: ClauseRiskResult[];
  overall_risk: number;
  severity_counts: SeverityCounts;
}

// ── Fix types ──────────────────────────────────────────────────────────────────

export interface FixCandidate {
  candidate_id: string;
  label: string;
  new_text: string;
  delta_overall: number;
  delta_clause_score: number;
  new_clause_level: string;
  rationale: string;
}

export interface SuggestFixResponse {
  block_id: string;
  original: string;
  candidates: FixCandidate[];
}

export interface AcceptFixResponse {
  block_id: string;
  new_clause_text: string;
  new_clause_score: ClauseRiskResult;
  new_overall_risk: number;
  new_severity_counts: SeverityCounts;
  version: string;
}

export interface DismissResponse {
  block_id: string;
  action: string;
  message: string;
}

export async function resetProtocol(protocolId: string): Promise<void> {
  // Best-effort: ignore failures (reset is a state-cleanup, not load-blocking)
  try {
    await apiFetch(`${BASE}/protocols/${protocolId}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    // swallow — proceed even if reset fails
  }
}

export async function suggestFix(
  protocolId: string,
  blockId: string,
  clauseText?: string
): Promise<SuggestFixResponse> {
  // For gen_ blocks (new typed clauses), the backend needs the live text to
  // try the text-pattern fix matcher. For seeded blk_ blocks the text is ignored.
  const body = clauseText ? { clause_text: clauseText } : {};
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/clauses/${blockId}/suggest-fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Suggest fix failed: ${res.status}`);
  return res.json() as Promise<SuggestFixResponse>;
}

export async function acceptFix(
  protocolId: string,
  blockId: string,
  candidateId: string
): Promise<AcceptFixResponse> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/clauses/${blockId}/accept-fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateId }),
  });
  if (!res.ok) throw new Error(`Accept fix failed: ${res.status}`);
  return res.json() as Promise<AcceptFixResponse>;
}

// ── Amendment package types ───────────────────────────────────────────────────

export interface AmendmentChange {
  clause_id: string;
  section: string;
  original_text: string;
  new_text: string;
  risk_before: number;
  risk_after: number;
  rationale: string;
  label: string;
  accepted_at: string;
}

export interface AmendmentPackageResponse {
  protocol_id: string;
  protocol_title: string;
  from_version: string;
  to_version: string;
  overall_risk_before: number;
  overall_risk_after: number;
  changes: AmendmentChange[];
  generated_at: string;
  markdown: string;
}

export async function fetchAmendmentPackage(
  protocolId: string
): Promise<AmendmentPackageResponse> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/amendment-package`);
  if (!res.ok) throw new Error(`Amendment package failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<AmendmentPackageResponse>;
}

export async function dismissFix(
  protocolId: string,
  blockId: string,
  reason?: string
): Promise<DismissResponse> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/clauses/${blockId}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason ?? "" }),
  });
  if (!res.ok) throw new Error(`Dismiss failed: ${res.status}`);
  return res.json() as Promise<DismissResponse>;
}

// ── Feasibility Simulator types ───────────────────────────────────────────────

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

// ── Drafting Agent types ──────────────────────────────────────────────────────

export interface DraftClauseResponse {
  topic: string;
  clause_text: string;
  generated_at: string;
  suggested_section: string | null;
  rationale: string | null;
}

// ── Gap Detection types ───────────────────────────────────────────────────────

export interface ProtocolGap {
  gap_id: string;
  name: string;
  category: string;
  rationale: string;
  suggested_section: string;
  suggested_section_id: string;
  draft_topic: string;
  regulatory_reference: string | null;
  severity: string;
}

export interface GapDetectionResponse {
  protocol_id: string;
  checklist_version: string;
  gaps_detected: ProtocolGap[];
  detected_at: string;
}

export async function detectGaps(
  protocolId: string,
  sectionTexts?: Record<string, string>
): Promise<GapDetectionResponse> {
  // sectionTexts: live per-section editor text. When provided, gap detection
  // reflects unsaved edits/deletions instead of the persisted seeded document.
  const body = sectionTexts ? { section_texts: sectionTexts } : {};
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/detect-gaps`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Gap detection failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<GapDetectionResponse>;
}

export async function draftClause(
  protocolId: string,
  topic: string,
  sectionId?: string,
  therapeuticArea = "diabetes"
): Promise<DraftClauseResponse> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/draft-clause`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, section_id: sectionId, therapeutic_area: therapeuticArea }),
  });
  if (!res.ok) {
    let detail = `Draft clause failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<DraftClauseResponse>;
}

export async function fetchFeasibility(protocolId: string): Promise<FeasibilityProjection> {
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/feasibility`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ include_baseline: true }),
  });
  if (!res.ok) {
    let detail = `Feasibility unavailable (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json() as Promise<FeasibilityProjection>;
}

export async function scoreProtocol(
  protocolId: string,
  blockIds?: string[],
  clauseTexts?: Record<string, string>
): Promise<ScoreResponse> {
  const body: Record<string, unknown> = {};
  if (blockIds) body.block_ids = blockIds;
  if (clauseTexts && Object.keys(clauseTexts).length > 0) body.clause_texts = clauseTexts;
  const res = await apiFetch(`${BASE}/protocols/${protocolId}/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Score fetch failed: ${res.status} ${res.statusText}`);
  return res.json() as Promise<ScoreResponse>;
}
