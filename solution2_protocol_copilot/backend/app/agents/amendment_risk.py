"""
Amendment-Risk LangGraph agent.
Wraps the scoring logic in a node for architectural consistency with the deck
(Amendment-Risk agent | Drafting light | Feasibility stubbed).
"""
import json
from typing import TypedDict, Any

from langgraph.graph import StateGraph, END

from app.config import settings, LLMMode
from app.schemas import ClauseRiskResult, FactorScore, PatternMatch, parse_llm_score_response
from app.utils.scoring import (
    score_clause_fake,
    score_clause_heuristic,
    compute_weighted_risk,
    risk_level,
    FACTOR_WEIGHTS,
)
from app.utils import llm_cache


class RiskState(TypedDict):
    block_id: str
    text: str
    section: str
    therapeutic_area: str
    target_countries: list[str]
    force_heuristic: bool   # Phase 5: when True, skip scripted lookup and heuristic-score the text
    mode_override: LLMMode | None   # Runtime mode toggle: per-request override of settings.llm_mode
    result: dict | None    # ClauseRiskResult-shaped dict


async def _score_live(state: RiskState, session: Any, mode: LLMMode) -> dict:
    """Live mode: embed → vector search → LLM scores 5 factors → weighted sum."""
    from app.utils.llm_mode_dependency import get_llm_client_for_mode
    from app.utils.vector_store import nearest_patterns
    import pathlib

    client = get_llm_client_for_mode(mode)
    text = state["text"]
    context = {"therapeutic_area": state["therapeutic_area"], "target_countries": state["target_countries"]}

    # 1. Embed the clause
    embedding = await client.embed(text)

    # 2. Nearest patterns from pgvector
    patterns = await nearest_patterns(session, embedding, k=3)

    # 3. Pattern match strength from top cosine similarity
    top_similarity = patterns[0]["similarity"] if patterns else 0.0
    pattern_match_score = round(max(0.0, min(1.0, top_similarity)) * 100)

    # 4. LLM scores the remaining 5 factors
    prompt_path = pathlib.Path(__file__).parent.parent / "prompts" / "score_clause.txt"
    prompt_template = prompt_path.read_text()
    prompt = prompt_template.format(
        clause_text=text,
        section=state["section"],
        therapeutic_area=state["therapeutic_area"],
        target_countries=", ".join(state["target_countries"]),
        patterns_json=json.dumps(patterns, indent=2),
        pattern_match_score=pattern_match_score,
    )

    raw = await client.complete(prompt, agent="amendment_risk", context=context)
    parsed = parse_llm_score_response(raw)

    if parsed is None:
        # Fallback to fake on parse failure
        return score_clause_fake(state["block_id"], text, state["target_countries"])

    # 5. Build factor dict — use vector cosine for pattern_match_strength
    factors: dict[str, int] = {"pattern_match_strength": pattern_match_score}
    for fname in FACTOR_WEIGHTS:
        if fname == "pattern_match_strength":
            continue
        fdata = parsed.get("factors", {}).get(fname, {})
        factors[fname] = int(fdata.get("score", 10))

    score = compute_weighted_risk(factors)
    level = risk_level(score)

    factor_objs = {}
    for fname in FACTOR_WEIGHTS:
        if fname == "pattern_match_strength":
            factor_objs[fname] = {"score": pattern_match_score, "reasoning": f"Cosine similarity to nearest pattern: {top_similarity:.3f}"}
        else:
            fdata = parsed.get("factors", {}).get(fname, {})
            factor_objs[fname] = {"score": int(fdata.get("score", 10)), "reasoning": fdata.get("reasoning", "")}

    top_match = None
    if patterns:
        tm = parsed.get("top_pattern_match") or {}
        top_match = {
            "pattern_id": tm.get("pattern_id", patterns[0]["pattern_id"]),
            "match_percent": pattern_match_score,
            "description": tm.get("description", patterns[0].get("category", "")),
        }

    return {
        "block_id": state["block_id"],
        "score": score,
        "risk_level": level,
        "factors": factor_objs,
        "top_pattern_match": top_match,
        "summary": parsed.get("summary", ""),
    }


async def score_node(state: RiskState, config: dict | None = None) -> RiskState:
    """LangGraph node: route by LLM mode and return scored result.
    Per-request mode override takes precedence over the env-var default."""
    session = (config or {}).get("configurable", {}).get("session")
    mode = state.get("mode_override") or settings.llm_mode

    if mode == LLMMode.LIVE:
        result = await _score_live(state, session, mode)
        # Write to cache for future cached-mode replay
        llm_cache.cache_set("score", state["text"], result, context={"ta": state["therapeutic_area"]})

    elif mode == LLMMode.CACHED:
        cached = llm_cache.cache_get("score", state["text"], context={"ta": state["therapeutic_area"]})
        if cached is not None:
            result = cached
        elif state["force_heuristic"]:
            result = score_clause_heuristic(state["block_id"], state["text"], state["target_countries"])
        else:
            result = score_clause_fake(state["block_id"], state["text"], state["target_countries"])

    else:  # mock | fake
        if state["force_heuristic"]:
            # Phase 5 live edit: skip the scripted lookup, run the heuristic on the live text
            result = score_clause_heuristic(state["block_id"], state["text"], state["target_countries"])
        else:
            result = score_clause_fake(state["block_id"], state["text"], state["target_countries"])

    return {**state, "result": result}


def build_risk_graph():
    graph: StateGraph = StateGraph(RiskState)
    graph.add_node("score", score_node)
    graph.set_entry_point("score")
    graph.add_edge("score", END)
    return graph.compile()


_RISK_GRAPH = build_risk_graph()


async def run_amendment_risk(
    block_id: str,
    text: str,
    section: str = "",
    therapeutic_area: str = "diabetes",
    target_countries: list[str] | None = None,
    session: Any = None,
    force_heuristic: bool = False,
    mode_override: LLMMode | None = None,
) -> ClauseRiskResult:
    """
    Public entry point — invoke the LangGraph Amendment-Risk agent for one clause.

    force_heuristic: when True (Phase 5 live edits with overridden text), the agent
    skips the scripted demo-clause lookup and runs the heuristic on the provided text.

    mode_override: per-request LLM mode (from the X-LLM-Mode header). When None,
    the agent uses settings.llm_mode (the env-var default).
    """
    initial: RiskState = {
        "block_id": block_id,
        "text": text,
        "section": section,
        "therapeutic_area": therapeutic_area,
        "target_countries": target_countries or ["US", "DE", "FR", "JP", "BR", "CN"],
        "force_heuristic": force_heuristic,
        "mode_override": mode_override,
        "result": None,
    }
    config = {"configurable": {"session": session}} if session else {}
    final = await _RISK_GRAPH.ainvoke(initial, config=config)
    raw = final["result"]

    # Convert raw dicts → Pydantic models
    factor_objs = {k: FactorScore(score=v["score"], reasoning=v["reasoning"]) for k, v in raw["factors"].items()}
    pm = raw.get("top_pattern_match")
    top_match = PatternMatch(**pm) if pm else None

    return ClauseRiskResult(
        block_id=raw["block_id"],
        score=raw["score"],
        risk_level=raw["risk_level"],
        factors=factor_objs,
        top_pattern_match=top_match,
        summary=raw["summary"],
    )
