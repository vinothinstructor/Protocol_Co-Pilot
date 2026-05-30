"""
Feasibility Simulator LangGraph agent.
Translates the abstract amendment-risk score into operational projections:
screen failure rate, sites required, time to LSI, enrollment cost savings.
All four LLM modes are implemented from day one.
"""
import json
import pathlib
from datetime import datetime, timezone
from typing import TypedDict

from app.config import LLMMode
from app.schemas import FeasibilityMetric, FeasibilityProjection

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_CACHE_PATH = pathlib.Path(__file__).parent.parent / "cache" / "feasibility_cache.json"
_PROMPT_PATH = pathlib.Path(__file__).parent.parent / "prompts" / "feasibility.txt"

# The three HIGH-risk demo blocks in the scripted demo arc order
_HIGH_BLOCKS = ("blk_4_4", "blk_4_3", "blk_6_2")

# Baseline risk for heuristic interpolation
_BASELINE_RISK = 73
_ALLFIX_RISK = 19


def _load_scripted() -> dict:
    return json.loads((_DATA_DIR / "demo_feasibility_projections.json").read_text())


def _delta_label(name: str, delta: float) -> str:
    if name == "screen_failure_rate":
        if delta == 0:
            return "no change"
        return f"{delta:+.0f} pts"
    if name == "sites_required":
        if delta == 0:
            return "no change"
        return f"{delta:+.0f} sites"
    if name == "time_to_lsi_weeks":
        if delta == 0:
            return "no change"
        return f"{delta:+.0f} wk"
    if name == "enrollment_cost_savings_usd_m":
        if delta == 0:
            return "no savings yet"
        return f"+${delta:.1f}M saved"
    return f"{delta:+.2f}"


def _build_projection(
    protocol_id: str,
    version: str,
    overall_risk: int,
    overall_risk_baseline: int,
    state_key: str,
    scripted: dict,
) -> FeasibilityProjection:
    baseline_data = scripted["v3.2_baseline"]["metrics"]
    current_data = scripted[state_key]["metrics"]
    rationale = scripted[state_key]["rationale"]

    metrics: list[FeasibilityMetric] = []
    for name in ("screen_failure_rate", "sites_required", "time_to_lsi_weeks", "enrollment_cost_savings_usd_m"):
        current_val = current_data[name]["value"]
        baseline_val = baseline_data[name]["value"]
        delta = current_val - baseline_val
        metrics.append(FeasibilityMetric(
            name=name,
            current_value=current_val,
            baseline_value=baseline_val,
            unit=current_data[name]["unit"],
            delta=delta,
            delta_label=_delta_label(name, delta),
        ))

    return FeasibilityProjection(
        protocol_id=protocol_id,
        protocol_version=version,
        overall_risk=overall_risk,
        overall_risk_baseline=overall_risk_baseline,
        metrics=metrics,
        rationale=rationale,
        generated_at=datetime.now(timezone.utc),
    )


def _heuristic_projection(
    protocol_id: str,
    version: str,
    overall_risk: int,
) -> FeasibilityProjection:
    """Linearly interpolate between baseline and after_all_three based on risk delta."""
    scripted = _load_scripted()
    baseline_data = scripted["v3.2_baseline"]["metrics"]
    allfix_data = scripted["after_all_three_fixes"]["metrics"]

    factor = max(0.0, min(1.0, (_BASELINE_RISK - overall_risk) / (_BASELINE_RISK - _ALLFIX_RISK)))

    metrics: list[FeasibilityMetric] = []
    for name in ("screen_failure_rate", "sites_required", "time_to_lsi_weeks", "enrollment_cost_savings_usd_m"):
        bval = baseline_data[name]["value"]
        aval = allfix_data[name]["value"]
        current_val = round(bval + factor * (aval - bval), 1)
        delta = current_val - bval
        metrics.append(FeasibilityMetric(
            name=name,
            current_value=current_val,
            baseline_value=bval,
            unit=baseline_data[name]["unit"],
            delta=delta,
            delta_label=_delta_label(name, delta),
        ))

    rationale = (
        f"Protocol amendment risk at {overall_risk}% — an improvement of "
        f"{_BASELINE_RISK - overall_risk} points from baseline. "
        "Operational projections interpolated from pattern-matched benchmark data."
    )
    return FeasibilityProjection(
        protocol_id=protocol_id,
        protocol_version=version,
        overall_risk=overall_risk,
        overall_risk_baseline=_BASELINE_RISK,
        metrics=metrics,
        rationale=rationale,
        generated_at=datetime.now(timezone.utc),
    )


def _mock_projection(protocol_id: str, version: str) -> FeasibilityProjection:
    metrics = [
        FeasibilityMetric(name=n, current_value=0.0, baseline_value=0.0,
                          unit=u, delta=0.0, delta_label="unavailable")
        for n, u in [
            ("screen_failure_rate", "%"),
            ("sites_required", "sites"),
            ("time_to_lsi_weeks", "weeks"),
            ("enrollment_cost_savings_usd_m", "$M"),
        ]
    ]
    return FeasibilityProjection(
        protocol_id=protocol_id,
        protocol_version=version,
        overall_risk=0,
        overall_risk_baseline=0,
        metrics=metrics,
        rationale="Mock mode — Feasibility Simulator not available.",
        generated_at=datetime.now(timezone.utc),
    )


def _load_feasibility_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_feasibility_cache(data: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(data, indent=2, default=str))


def _cache_key(protocol_id: str, accepted_block_ids: frozenset) -> str:
    import hashlib
    payload = json.dumps({"pid": protocol_id, "accepted": sorted(accepted_block_ids)}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


async def project_feasibility(
    protocol_id: str,
    version: str,
    overall_risk: int,
    accepted_block_ids: set[str],
    mode: LLMMode,
    protocol_doc: dict | None = None,
) -> FeasibilityProjection:
    """
    Core feasibility projection logic, called from the router.
    Routes to the correct mode implementation.
    """
    if mode == LLMMode.MOCK:
        return _mock_projection(protocol_id, version)

    if mode in (LLMMode.FAKE, LLMMode.CACHED):
        if mode == LLMMode.CACHED:
            cache = _load_feasibility_cache()
            key = _cache_key(protocol_id, frozenset(accepted_block_ids))
            if key in cache:
                entry = cache[key]
                # Re-hydrate datetime strings
                if isinstance(entry.get("generated_at"), str):
                    entry["generated_at"] = datetime.fromisoformat(entry["generated_at"])
                return FeasibilityProjection(**entry)
            # Cache miss — fall through to fake

        scripted = _load_scripted()
        drug_naive = "blk_4_4" in accepted_block_ids
        bmi = "blk_4_3" in accepted_block_ids
        visits = "blk_6_2" in accepted_block_ids

        if drug_naive and bmi and visits:
            state_key = "after_all_three_fixes"
        elif drug_naive and bmi:
            state_key = "after_drug_naive_and_bmi_fixes"
        elif drug_naive and not bmi and not visits:
            state_key = "after_drug_naive_fix"
        elif not drug_naive and not bmi and not visits:
            state_key = "v3.2_baseline"
        else:
            return _heuristic_projection(protocol_id, version, overall_risk)

        return _build_projection(
            protocol_id=protocol_id,
            version=version,
            overall_risk=overall_risk,
            overall_risk_baseline=_BASELINE_RISK,
            state_key=state_key,
            scripted=scripted,
        )

    if mode == LLMMode.LIVE:
        return await _live_projection(
            protocol_id=protocol_id,
            version=version,
            overall_risk=overall_risk,
            accepted_block_ids=accepted_block_ids,
            protocol_doc=protocol_doc,
        )

    return _mock_projection(protocol_id, version)


async def _live_projection(
    protocol_id: str,
    version: str,
    overall_risk: int,
    accepted_block_ids: set[str],
    protocol_doc: dict | None,
) -> FeasibilityProjection:
    from app.utils.llm_mode_dependency import get_llm_client_for_mode
    from app.utils.vector_store import nearest_patterns
    from app.db.session import AsyncSessionLocal

    client = get_llm_client_for_mode(LLMMode.LIVE)

    # Get a few top patterns to ground the prompt
    patterns_summary = []
    try:
        dummy_embedding = await client.embed("diabetes inclusion criteria")
        async with AsyncSessionLocal() as session:
            patterns = await nearest_patterns(session, dummy_embedding, k=3)
        patterns_summary = patterns
    except Exception:
        patterns_summary = []

    doc = protocol_doc or {}
    title = doc.get("title", "Phase III Diabetes Protocol")
    therapeutic_area = doc.get("therapeutic_area", "Type 2 Diabetes Mellitus")
    target_countries = ", ".join(doc.get("target_countries", ["US", "Brazil", "Poland"]))

    prompt_template = _PROMPT_PATH.read_text()
    prompt = prompt_template.format(
        protocol_title=title,
        therapeutic_area=therapeutic_area,
        target_countries=target_countries,
        overall_risk=overall_risk,
        overall_risk_baseline=_BASELINE_RISK,
        patterns_json=json.dumps(patterns_summary, indent=2),
    )

    raw = await client.complete(prompt, agent="feasibility_simulator")

    # Parse the JSON response
    import re
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return _heuristic_projection(protocol_id, version, overall_risk)

    baseline_data = _load_scripted()["v3.2_baseline"]["metrics"]
    rationale = data.get("rationale", "Projections generated by live LLM call.")

    metrics: list[FeasibilityMetric] = []
    for name in ("screen_failure_rate", "sites_required", "time_to_lsi_weeks", "enrollment_cost_savings_usd_m"):
        current_val = float(data.get(name, 0.0))
        baseline_val = baseline_data[name]["value"]
        delta = current_val - baseline_val
        metrics.append(FeasibilityMetric(
            name=name,
            current_value=current_val,
            baseline_value=baseline_val,
            unit=baseline_data[name]["unit"],
            delta=delta,
            delta_label=_delta_label(name, delta),
        ))

    proj = FeasibilityProjection(
        protocol_id=protocol_id,
        protocol_version=version,
        overall_risk=overall_risk,
        overall_risk_baseline=_BASELINE_RISK,
        metrics=metrics,
        rationale=rationale,
        generated_at=datetime.now(timezone.utc),
    )

    # Write to cache for next time
    cache = _load_feasibility_cache()
    key = _cache_key(protocol_id, frozenset(accepted_block_ids))
    cache[key] = proj.model_dump()
    _save_feasibility_cache(cache)

    return proj
