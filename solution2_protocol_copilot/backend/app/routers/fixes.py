"""
Suggest-Fix and Accept-Fix endpoints.
All demo-mode behavior is driven by demo_fix_candidates.json + demo_clause_scores.json.
"""
import json
import pathlib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.db.session import get_session
from app.db.models import ProtocolVersion, ClauseHistory, AmendmentPattern
from datetime import datetime, timezone

from app.schemas import (
    FixCandidate, SuggestFixRequest, SuggestFixResponse,
    AcceptFixRequest, AcceptFixResponse,
    DismissRequest, DismissResponse,
    ClauseRiskResult, FactorScore, PatternMatch, SeverityCounts,
    AmendmentChange, AmendmentPackageResponse,
)
from app.utils.scoring import compute_overall_risk
from app.utils.amendment_package import render_markdown
from app.utils.llm_mode_dependency import resolve_llm_mode, get_llm_client_for_mode
from app.config import settings, LLMMode

router = APIRouter()
DATA_DIR = pathlib.Path(__file__).parent.parent / "data"

# ── Data loading ───────────────────────────────────────────────────────────────

def _load_raw_candidates() -> dict:
    """Return demo_fix_candidates.json as-is (including _text_patterns)."""
    return json.loads((DATA_DIR / "demo_fix_candidates.json").read_text())


def _load_demo_scores() -> dict:
    raw = json.loads((DATA_DIR / "demo_clause_scores.json").read_text())
    return {k: v for k, v in raw.items() if not k.startswith("_")}


_FIX_CANDIDATES_RAW = _load_raw_candidates()
_FIX_CANDIDATES = {k: v for k, v in _FIX_CANDIDATES_RAW.items() if not k.startswith("_")}
_TEXT_PATTERNS: dict = _FIX_CANDIDATES_RAW.get("_text_patterns", {})
_DEMO_SCORES = _load_demo_scores()

# All 20 scored block IDs (order: HIGH → MEDIUM → LOW)
_SCORED_BLOCKS = list(_DEMO_SCORES.keys())


# ── Helpers ────────────────────────────────────────────────────────────────────

def _match_text_pattern(text: str) -> dict | None:
    """Return the matched _text_patterns entry (with candidates) for a clause's text."""
    if not text:
        return None
    tl = text.lower()
    for pattern in _TEXT_PATTERNS.values():
        keywords = [k.lower() for k in pattern.get("match_keywords", [])]
        if not keywords:
            continue
        if pattern.get("match_all_required", True):
            if all(k in tl for k in keywords):
                return pattern
        else:
            if any(k in tl for k in keywords):
                return pattern
    return None


def _get_candidate(block_id: str, candidate_id: str) -> FixCandidate | None:
    """Look up a candidate by id across both block-keyed and text-pattern-keyed entries."""
    # 1. Block-keyed (seeded blk_X_X)
    entry = _FIX_CANDIDATES.get(block_id)
    if entry:
        for c in entry["candidates"]:
            if c["candidate_id"] == candidate_id:
                return FixCandidate(**c)
    # 2. Text-pattern (gen_X clauses matched by content)
    for pattern in _TEXT_PATTERNS.values():
        for c in pattern.get("candidates", []):
            if c["candidate_id"] == candidate_id:
                return FixCandidate(**c)
    return None


def _candidate_by_new_text(block_id: str, new_text: str) -> dict | None:
    """Reverse lookup: given an accepted clause's new_text, find the source candidate
    (carries `rationale` and `label` for the amendment package)."""
    entry = _FIX_CANDIDATES.get(block_id)
    if entry:
        for c in entry["candidates"]:
            if c["new_text"] == new_text:
                return c
    for pattern in _TEXT_PATTERNS.values():
        for c in pattern.get("candidates", []):
            if c["new_text"] == new_text:
                return c
    return None


def _bump_version(version: str) -> str:
    """v3.2 → v3.3"""
    v, rest = version.lstrip("v"), None
    if "." in v:
        major, minor = v.split(".", 1)
        return f"v{major}.{int(minor) + 1}"
    return f"v{v}.1"


def _find_clause(doc: dict, block_id: str) -> tuple[str, str] | None:
    """Returns (section_heading, clause_text) or None."""
    for section in doc.get("sections", []):
        for block in section.get("blocks", []):
            if block["block_id"] == block_id:
                return section["heading"], block["text"]
    return None


def _apply_clause_text(doc: dict, block_id: str, new_text: str) -> dict:
    """Return a deep-ish copy of doc with the clause text replaced."""
    import copy
    doc = copy.deepcopy(doc)
    for section in doc.get("sections", []):
        for block in section.get("blocks", []):
            if block["block_id"] == block_id:
                block["text"] = new_text
                return doc
    return doc


async def _get_accepted_fixes(protocol_id: str, session: AsyncSession) -> dict[str, str]:
    """Returns {block_id: new_clause_level} for all accepted fixes."""
    rows = (
        await session.execute(
            select(ClauseHistory).where(
                ClauseHistory.protocol_id == protocol_id,
                ClauseHistory.action == "accept",
            )
        )
    ).scalars().all()
    return {r.clause_id: r.new_text for r in rows}


def _compute_severity_with_fixes(accepted_fixes: dict[str, str]) -> SeverityCounts:
    """
    Compute n_high/n_medium/n_low across all 20 scored blocks.
    For accepted blocks, their new_clause_level is read from _FIX_CANDIDATES.
    For others, use the scripted level from _DEMO_SCORES.
    """
    n_high = n_medium = n_low = 0

    # Build a lookup of accepted block_id → new_clause_level
    accepted_levels: dict[str, str] = {}
    for block_id, new_text in accepted_fixes.items():
        for c_list in _FIX_CANDIDATES.get(block_id, {}).get("candidates", []):
            if c_list["new_text"] == new_text:
                accepted_levels[block_id] = c_list["new_clause_level"]
                break
        if block_id not in accepted_levels:
            accepted_levels[block_id] = "low"  # safe default

    for bid in _SCORED_BLOCKS:
        if bid in accepted_levels:
            level = accepted_levels[bid]
        else:
            level = _DEMO_SCORES[bid]["risk_level"]

        if level == "high":
            n_high += 1
        elif level == "medium":
            n_medium += 1
        else:
            n_low += 1

    return SeverityCounts(high=n_high, medium=n_medium, low=n_low)


def _make_fixed_clause_result(block_id: str, candidate: FixCandidate) -> ClauseRiskResult:
    """Build a post-fix ClauseRiskResult showing the improved factors."""
    original = _DEMO_SCORES.get(block_id, {})
    original_score = original.get("score", 20)
    new_score = max(1, min(100, original_score + candidate.delta_clause_score))

    low_factors = {
        name: FactorScore(score=5, reasoning="Clause revised to address the root cause of amendment risk.")
        for name in ["pattern_match_strength", "therapeutic_area_fit", "operational_complexity",
                     "inclusion_restrictiveness", "endpoint_instrument_validation", "visit_burden"]
    }
    return ClauseRiskResult(
        block_id=block_id,
        score=new_score,
        risk_level=candidate.new_clause_level,
        factors=low_factors,
        top_pattern_match=None,
        summary=f"Clause revised: {candidate.label}. Amendment risk substantially reduced.",
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/protocols/{protocol_id}/clauses/{block_id}/suggest-fix",
             response_model=SuggestFixResponse)
async def suggest_fix(
    protocol_id: str,
    block_id: str,
    body: SuggestFixRequest = SuggestFixRequest(),
    session: AsyncSession = Depends(get_session),
    mode: LLMMode = Depends(resolve_llm_mode),
):
    if mode == LLMMode.LIVE:
        # Live mode: call LLM (cached result written back)
        from app.utils import llm_cache
        import pathlib as _pl

        ctx = {"protocol_id": protocol_id, "block_id": block_id}
        cached = llm_cache.cache_get("suggest_fix", block_id, context=ctx)
        if cached:
            return SuggestFixResponse(**cached)

        # Fetch clause context
        row = (
            await session.execute(
                select(ProtocolVersion)
                .where(ProtocolVersion.protocol_id == protocol_id)
                .order_by(ProtocolVersion.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(404, f"Protocol {protocol_id} not found")

        clause_info = _find_clause(row.document, block_id)
        if clause_info:
            _, clause_text = clause_info
        elif body.clause_text:
            clause_text = body.clause_text
        else:
            raise HTTPException(404, f"Block {block_id} not found")

        # Build prompt
        prompt_path = _pl.Path(__file__).parent.parent / "prompts" / "suggest_fix.txt"
        prompt = prompt_path.read_text().format(
            clause_text=clause_text,
            block_id=block_id,
            therapeutic_area=row.document.get("therapeutic_area", "diabetes"),
        )
        client = get_llm_client_for_mode(mode)
        raw = await client.complete(prompt, agent="suggest_fix", context=ctx)

        from app.schemas import parse_llm_fix_response
        parsed = parse_llm_fix_response(raw)
        if parsed:
            result = SuggestFixResponse(block_id=block_id, original=clause_text,
                                        candidates=[FixCandidate(**c) for c in parsed["candidates"]])
            llm_cache.cache_set("suggest_fix", block_id, result.model_dump(), context=ctx)
            return result

    # ── Fake / cached / mock mode ─────────────────────────────────────────────
    # 1. Block-keyed: scripted candidates for seeded blocks (blk_X_X)
    entry = _FIX_CANDIDATES.get(block_id)
    if entry:
        return SuggestFixResponse(
            block_id=block_id,
            original=entry["original"],
            candidates=[FixCandidate(**c) for c in entry["candidates"]],
        )

    # 2. Text-pattern: match by clause content (typically gen_ ids from new clauses)
    if body.clause_text:
        pattern = _match_text_pattern(body.clause_text)
        if pattern:
            return SuggestFixResponse(
                block_id=block_id,
                original=body.clause_text,
                candidates=[FixCandidate(**c) for c in pattern["candidates"]],
            )

    # 3. No match — return empty candidates list. The frontend interprets this
    # as "custom clause, edit manually" and hides the Suggest Fix button.
    return SuggestFixResponse(
        block_id=block_id,
        original=body.clause_text or "",
        candidates=[],
    )


@router.post("/protocols/{protocol_id}/clauses/{block_id}/accept-fix",
             response_model=AcceptFixResponse)
async def accept_fix(
    protocol_id: str,
    block_id: str,
    body: AcceptFixRequest,
    session: AsyncSession = Depends(get_session),
    mode: LLMMode = Depends(resolve_llm_mode),
):
    _ = mode  # accept-fix is deterministic over scripted candidates; mode is
              # accepted so the header doesn't 422 on its presence, but the
              # fix application doesn't consult the LLM.
    candidate = _get_candidate(block_id, body.candidate_id)
    if not candidate:
        raise HTTPException(404, f"Candidate {body.candidate_id} not found for block {block_id}")

    # Load latest protocol version
    row = (
        await session.execute(
            select(ProtocolVersion)
            .where(ProtocolVersion.protocol_id == protocol_id)
            .order_by(ProtocolVersion.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"Protocol {protocol_id} not found")

    # ── Gen_ branch: not a seeded block; no DB persistence ────────────────────
    # The candidate declares its own new_clause_level; trust it rather than
    # re-running the heuristic on the candidate text (which can spuriously flag
    # negation contexts like "not the native language" as PRO validation risk).
    if not block_id.startswith("blk_"):
        # Build the post-fix clause result from the candidate's declared level
        new_clause_score = _make_fixed_clause_result(block_id, candidate)

        # Compute aggregate: 20 demo blocks at their scripted levels +
        # this gen_ clause at its post-fix level.
        accepted = await _get_accepted_fixes(protocol_id, session)
        counts = _compute_severity_with_fixes(accepted)
        # Add the gen_ block's contribution
        if candidate.new_clause_level == "high":
            counts.high += 1
        elif candidate.new_clause_level == "medium":
            counts.medium += 1
        else:
            counts.low += 1
        overall = compute_overall_risk(counts.high, counts.medium, counts.low)

        return AcceptFixResponse(
            block_id=block_id,
            new_clause_text=candidate.new_text,
            new_clause_score=new_clause_score,
            new_overall_risk=overall,
            new_severity_counts=counts,
            version=row.version,  # no version bump for ephemeral gen_ clauses
        )

    # ── Seeded block branch (blk_X_X) ────────────────────────────────────────
    # Phase 7 update: Accept-fix records the fix in clause_history for audit
    # but does NOT bump the protocol version or create a new ProtocolVersion.
    # The version bump happens exactly once per amendment-package generation
    # (see GET /protocols/{id}/amendment-package), so a reviewer sees one
    # version delta per package regardless of how many fixes it contains.
    clause_info = _find_clause(row.document, block_id)
    if not clause_info:
        raise HTTPException(404, f"Block {block_id} not found in protocol document")
    _, original_text = clause_info

    # Idempotency: if a row already exists for this (clause, new_text) pair,
    # don't insert a duplicate — just return the current state.
    existing = (
        await session.execute(
            select(ClauseHistory).where(
                ClauseHistory.protocol_id == protocol_id,
                ClauseHistory.clause_id == block_id,
                ClauseHistory.action == "accept",
                ClauseHistory.new_text == candidate.new_text,
            ).limit(1)
        )
    ).scalar_one_or_none()

    if existing is None:
        original_score = _DEMO_SCORES.get(block_id, {}).get("score", 50)
        new_score = max(1, min(100, original_score + candidate.delta_clause_score))
        session.add(ClauseHistory(
            protocol_id=protocol_id,
            clause_id=block_id,
            action="accept",
            original_text=original_text,
            new_text=candidate.new_text,
            risk_before=original_score,
            risk_after=new_score,
        ))
        await session.commit()

    # Compute new overall from cumulative accepts
    accepted = await _get_accepted_fixes(protocol_id, session)
    counts = _compute_severity_with_fixes(accepted)
    overall = compute_overall_risk(counts.high, counts.medium, counts.low)

    return AcceptFixResponse(
        block_id=block_id,
        new_clause_text=candidate.new_text,
        new_clause_score=_make_fixed_clause_result(block_id, candidate),
        new_overall_risk=overall,
        new_severity_counts=counts,
        version=row.version,  # latest persisted version; bumps only on package generation
    )


@router.post("/protocols/{protocol_id}/reset")
async def reset_protocol(
    protocol_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Reset the protocol to its baseline state: clear all clause_history and remove
    any protocol_versions beyond the original (v3.2). Called by the frontend on
    mount so each page-load shows the demo's 73% baseline, not the residue of a
    previous session's accepts.
    """
    await session.execute(
        delete(ClauseHistory).where(ClauseHistory.protocol_id == protocol_id)
    )
    await session.execute(
        delete(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version != "v3.2",
        )
    )
    await session.commit()
    return {"protocol_id": protocol_id, "reset": True, "version": "v3.2"}


@router.post("/protocols/{protocol_id}/clauses/{block_id}/dismiss",
             response_model=DismissResponse)
async def dismiss_fix(
    protocol_id: str,
    block_id: str,
    body: DismissRequest,
    session: AsyncSession = Depends(get_session),
):
    original_score = _DEMO_SCORES.get(block_id, {}).get("score", 50)
    session.add(ClauseHistory(
        protocol_id=protocol_id,
        clause_id=block_id,
        action="dismiss",
        original_text=body.reason or "",
        new_text="",
        risk_before=original_score,
        risk_after=original_score,
    ))
    await session.commit()
    return DismissResponse(
        block_id=block_id,
        action="dismiss",
        message="Clause dismissed. Risk score unchanged; recorded in audit trail.",
    )


# ── Amendment package (Phase 7 export closer) ─────────────────────────────────

def _section_label_for_block(doc: dict, block_id: str) -> str:
    """Return 'Section N — Heading' for the given block_id, or a fallback."""
    for section in doc.get("sections", []):
        for block in section.get("blocks", []):
            if block["block_id"] == block_id:
                return f"Section {section['number']} — {section['heading']}"
    return f"Block {block_id}"


@router.get("/protocols/{protocol_id}/amendment-package",
            response_model=AmendmentPackageResponse)
async def amendment_package(
    protocol_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Assemble an amendment package from the accepted fixes for this protocol.

    Versioning model (Phase 7 update):
    - Accept-fix calls record changes in clause_history but do NOT bump the
      protocol version. The current latest persisted version stays as-is until
      a package is generated.
    - This endpoint bumps the version by exactly ONE minor on first call after
      a batch of accepts (e.g., v3.2 → v3.3), creating one ProtocolVersion row
      that snapshots the cumulative document after all accepts.
    - Idempotent: calling again with no new accepts returns the existing latest
      package (no double-bump).
    - If more fixes are accepted after a package is generated, the next call
      bumps once more (e.g., v3.3 → v3.4) and includes only the newly accepted
      changes in that package.
    """
    import copy as _copy

    # 1. All accepts for this protocol, chronological
    all_accepts = (
        await session.execute(
            select(ClauseHistory).where(
                ClauseHistory.protocol_id == protocol_id,
                ClauseHistory.action == "accept",
            ).order_by(ClauseHistory.created_at)
        )
    ).scalars().all()

    if not all_accepts:
        raise HTTPException(400, "No accepted amendments to export")

    # 2. All versions for this protocol, chronological
    versions = (
        await session.execute(
            select(ProtocolVersion).where(ProtocolVersion.protocol_id == protocol_id)
            .order_by(ProtocolVersion.created_at)
        )
    ).scalars().all()

    if not versions:
        raise HTTPException(404, f"Protocol {protocol_id} not found")

    latest = versions[-1]
    baseline_doc = versions[0].document  # v3.2 source
    protocol_title = baseline_doc.get("title", "Untitled Protocol")

    # 3. Compute overall risk arc once (always 73 baseline → current count)
    accepted_levels = await _get_accepted_fixes(protocol_id, session)
    counts_after = _compute_severity_with_fixes(accepted_levels)
    overall_after = compute_overall_risk(counts_after.high, counts_after.medium, counts_after.low)
    overall_before = compute_overall_risk(3, 5, 12)  # seeded baseline = 73

    # 4. Decide: do we need to bump? (Are there accepts after the latest version?)
    unpackaged = [a for a in all_accepts if a.created_at > latest.created_at]

    if unpackaged:
        # Build cumulative document by applying ALL accepts to the baseline
        new_doc = _copy.deepcopy(baseline_doc)
        for a in all_accepts:
            new_doc = _apply_clause_text(new_doc, a.clause_id, a.new_text or "")

        new_version_str = _bump_version(latest.version)
        new_pv = ProtocolVersion(
            protocol_id=protocol_id,
            version=new_version_str,
            document=new_doc,
            overall_risk=overall_after,
        )
        session.add(new_pv)
        await session.commit()
        await session.refresh(new_pv)

        from_version_str = latest.version
        to_version_pv = new_pv
        package_accepts = unpackaged   # only the new accepts go into THIS package
    else:
        # Idempotent: latest already covers the current set of accepts.
        # from_version = the version BEFORE latest.
        if len(versions) >= 2:
            from_version_str = versions[-2].version
            to_version_pv = latest
            # Changes are accepts within (prev_version.created_at, latest.created_at]
            prev = versions[-2]
            package_accepts = [
                a for a in all_accepts
                if prev.created_at < a.created_at <= latest.created_at
            ]
        else:
            # Only the baseline v3.2 exists and there's no version after it,
            # yet accepts exist that aren't unpackaged — shouldn't happen because
            # accepts always have created_at > v3.2.created_at (else they'd predate it).
            # Defensive fallback: include all accepts and reuse latest as both endpoints.
            from_version_str = latest.version
            to_version_pv = latest
            package_accepts = all_accepts

    # 5. Build AmendmentChange list from THIS package's accepts only
    changes: list[AmendmentChange] = []
    for r in package_accepts:
        candidate = _candidate_by_new_text(r.clause_id, r.new_text or "")
        rationale = (candidate.get("rationale", "Rationale not available.")
                     if candidate else "Rationale not available.")
        label = candidate.get("label", "Manual revision") if candidate else "Manual revision"
        section = _section_label_for_block(baseline_doc, r.clause_id)
        changes.append(AmendmentChange(
            clause_id=r.clause_id,
            section=section,
            original_text=r.original_text or "",
            new_text=r.new_text or "",
            risk_before=r.risk_before or 0,
            risk_after=r.risk_after or 0,
            rationale=rationale,
            label=label,
            accepted_at=r.created_at,
        ))

    generated_at = datetime.now(timezone.utc)
    markdown = render_markdown(
        protocol_id=protocol_id,
        protocol_title=protocol_title,
        from_version=from_version_str,
        to_version=to_version_pv.version,
        overall_risk_before=overall_before,
        overall_risk_after=overall_after,
        changes=changes,
        generated_at=generated_at,
    )

    return AmendmentPackageResponse(
        protocol_id=protocol_id,
        protocol_title=protocol_title,
        from_version=from_version_str,
        to_version=to_version_pv.version,
        overall_risk_before=overall_before,
        overall_risk_after=overall_after,
        changes=changes,
        generated_at=generated_at,
        markdown=markdown,
    )
