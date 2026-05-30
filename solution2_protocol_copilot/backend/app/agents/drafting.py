"""
Drafting Agent — generates new protocol clauses from a topic prompt.
Follows the same 4-mode discipline as the Amendment-Risk and Feasibility agents.
"""
import json
import pathlib
import re
from datetime import datetime, timezone

from app.config import LLMMode
from app.schemas import DraftClauseResponse, ProtocolGap, GapDetectionResponse

_DATA_DIR = pathlib.Path(__file__).parent.parent / "data"
_CACHE_PATH = pathlib.Path(__file__).parent.parent / "cache" / "drafting_cache.json"
_GAP_CACHE_PATH = pathlib.Path(__file__).parent.parent / "cache" / "gap_cache.json"
_PROMPT_PATH = pathlib.Path(__file__).parent.parent / "prompts" / "draft_clause.txt"
_CHECKLIST_PATH = _DATA_DIR / "protocol_gap_checklist.json"


def _load_scripted() -> dict:
    return json.loads((_DATA_DIR / "demo_drafted_clauses.json").read_text())


def _match_scripted(topic: str) -> dict | None:
    """Return the first scripted entry whose keywords appear in the normalized topic."""
    normalized = topic.lower()
    for entry in _load_scripted().values():
        for kw in entry.get("match_keywords", []):
            if kw.lower() in normalized:
                return entry
    return None


def _heuristic_fallback_clause(topic: str) -> str:
    return (
        f"Subjects must meet the following criterion related to {topic.lower()}: "
        f"[criterion to be drafted by Medical Director review]. "
        f"This requirement is consistent with standard practice for Phase III studies "
        f"in this therapeutic area."
    )


def _cache_key(topic: str) -> str:
    import hashlib
    return hashlib.sha256(topic.lower().strip().encode()).hexdigest()[:16]


def _load_cache() -> dict:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(data: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(data, indent=2, default=str))


async def draft_clause(
    topic: str,
    therapeutic_area: str,
    section: str,
    mode: LLMMode,
) -> DraftClauseResponse:
    now = datetime.now(timezone.utc)

    if mode == LLMMode.MOCK:
        return DraftClauseResponse(
            topic=topic,
            clause_text=f"[Mock clause for {topic} — switch to FAKE/CACHED/LIVE for content]",
            generated_at=now,
            suggested_section=None,
            rationale=None,
        )

    if mode in (LLMMode.FAKE, LLMMode.CACHED):
        if mode == LLMMode.CACHED:
            cache = _load_cache()
            key = _cache_key(topic)
            if key in cache:
                entry = cache[key]
                return DraftClauseResponse(
                    topic=topic,
                    clause_text=entry["clause_text"],
                    generated_at=now,
                    suggested_section=entry.get("suggested_section"),
                    rationale=entry.get("rationale"),
                )
            # Cache miss — fall through to scripted/heuristic

        scripted = _match_scripted(topic)
        if scripted:
            return DraftClauseResponse(
                topic=topic,
                clause_text=scripted["clause_text"],
                generated_at=now,
                suggested_section=scripted.get("suggested_section"),
                rationale=scripted.get("rationale"),
            )

        return DraftClauseResponse(
            topic=topic,
            clause_text=_heuristic_fallback_clause(topic),
            generated_at=now,
            suggested_section=None,
            rationale="Heuristic fallback — topic not in scripted library. Medical Director review required.",
        )

    if mode == LLMMode.LIVE:
        return await _live_draft(topic, therapeutic_area, section, now)

    return DraftClauseResponse(
        topic=topic,
        clause_text=_heuristic_fallback_clause(topic),
        generated_at=now,
    )


async def _live_draft(topic: str, therapeutic_area: str, section: str, now: datetime) -> DraftClauseResponse:
    from app.utils.llm_mode_dependency import get_llm_client_for_mode

    client = get_llm_client_for_mode(LLMMode.LIVE)  # raises RuntimeError if no Azure creds

    prompt_template = _PROMPT_PATH.read_text()
    prompt = prompt_template.format(
        therapeutic_area=therapeutic_area,
        section=section or "appropriate protocol section",
        topic=topic,
    )

    raw = await client.complete(prompt, agent="drafting")

    def _parse(text: str) -> dict | None:
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        try:
            data = json.loads(cleaned)
            return data if "clause_text" in data else None
        except (json.JSONDecodeError, ValueError):
            return None

    parsed = _parse(raw)
    if parsed is None:
        # Retry once with a stricter prompt
        strict_prompt = prompt + "\n\nIMPORTANT: Return ONLY the JSON object, nothing else."
        raw2 = await client.complete(strict_prompt, agent="drafting")
        parsed = _parse(raw2)

    if parsed is None:
        raise RuntimeError("LLM response could not be parsed.")

    clause_text = parsed["clause_text"]
    suggested_section = parsed.get("suggested_section")
    rationale = parsed.get("rationale")

    # Write to cache
    cache = _load_cache()
    key = _cache_key(topic)
    cache[key] = {"clause_text": clause_text, "suggested_section": suggested_section, "rationale": rationale}
    _save_cache(cache)

    return DraftClauseResponse(
        topic=topic,
        clause_text=clause_text,
        generated_at=now,
        suggested_section=suggested_section,
        rationale=rationale,
    )


# ── Gap Detection ──────────────────────────────────────────────────────────────

def _load_checklist() -> list[dict]:
    return json.loads(_CHECKLIST_PATH.read_text())["diabetes_phase_iii"]["gaps"]


def _checklist_version() -> str:
    return json.loads(_CHECKLIST_PATH.read_text())["diabetes_phase_iii"]["checklist_version"]


def _build_section_text(
    protocol: dict,
    section_texts_override: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return {section_id: combined_lower_text} for all sections.

    When section_texts_override is provided (live editor state from the
    frontend), it takes precedence over the persisted document so gap
    detection reflects unsaved edits/deletions.
    """
    if section_texts_override is not None:
        return {sid: (text or "").lower() for sid, text in section_texts_override.items()}
    result: dict[str, str] = {}
    for section in protocol.get("sections", []):
        combined = " ".join(b.get("text", "") for b in section.get("blocks", []))
        result[section["section_id"]] = combined.lower()
    return result


def _is_gap_missing(gap_entry: dict, section_text: dict[str, str]) -> bool:
    """True if NONE of the detection keywords appear in the relevant sections."""
    combined = " ".join(section_text.get(s, "") for s in gap_entry["detection_sections"])
    return not any(kw.lower() in combined for kw in gap_entry["detection_keywords_any"])


def _entry_to_gap(entry: dict) -> ProtocolGap:
    return ProtocolGap(
        gap_id=entry["gap_id"],
        name=entry["name"],
        category=entry["category"],
        rationale=entry["rationale"],
        suggested_section=entry["suggested_section"],
        suggested_section_id=entry["suggested_section_id"],
        draft_topic=entry["draft_topic"],
        regulatory_reference=entry.get("regulatory_reference"),
        severity=entry.get("severity", "recommended"),
    )


def _detect_gaps_via_checklist(
    protocol: dict,
    featured_only: bool = False,
    section_texts_override: dict[str, str] | None = None,
) -> list[ProtocolGap]:
    """Deterministic keyword scan against the reference checklist."""
    checklist = _load_checklist()
    section_text = _build_section_text(protocol, section_texts_override)
    gaps: list[ProtocolGap] = []
    for entry in checklist:
        if featured_only and not entry.get("featured", False):
            continue
        if _is_gap_missing(entry, section_text):
            gaps.append(_entry_to_gap(entry))
    return gaps


def _load_gap_cache() -> dict:
    if _GAP_CACHE_PATH.exists():
        try:
            return json.loads(_GAP_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_gap_cache(data: dict) -> None:
    _GAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GAP_CACHE_PATH.write_text(json.dumps(data, indent=2, default=str))


def _gap_cache_key(protocol_id: str) -> str:
    import hashlib
    return hashlib.sha256(protocol_id.encode()).hexdigest()[:16]


def _placeholder_gap() -> ProtocolGap:
    return ProtocolGap(
        gap_id="GAP_MOCK",
        name="[Mock gap — switch to FAKE/CACHED/LIVE for content]",
        category="mock",
        rationale="Mock mode active.",
        suggested_section="Section 5 — Exclusion Criteria",
        suggested_section_id="sec_5",
        draft_topic="mock topic",
        regulatory_reference=None,
        severity="optional",
    )


async def detect_gaps(
    protocol_id: str,
    protocol: dict,
    mode: LLMMode,
    section_texts_override: dict[str, str] | None = None,
) -> GapDetectionResponse:
    now = datetime.now(timezone.utc)
    version = _checklist_version()

    if mode == LLMMode.MOCK:
        gaps = [_placeholder_gap()]

    elif mode == LLMMode.FAKE:
        # Featured-only: return only the demo-priority gaps that are missing
        gaps = _detect_gaps_via_checklist(
            protocol, featured_only=True, section_texts_override=section_texts_override
        )

    elif mode == LLMMode.CACHED:
        # When live editor state is provided, prefer deterministic detection over
        # the static cache so deletions/edits are reflected. Use cache only for
        # the initial (no-override) load.
        if section_texts_override is not None:
            gaps = _detect_gaps_via_checklist(
                protocol, featured_only=True, section_texts_override=section_texts_override
            )
        else:
            cache = _load_gap_cache()
            key = _gap_cache_key(protocol_id)
            if key in cache:
                gaps = [ProtocolGap(**g) for g in cache[key]]
            else:
                gaps = _detect_gaps_via_checklist(protocol, featured_only=True)

    elif mode == LLMMode.LIVE:
        gaps = await _detect_gaps_live(protocol_id, protocol, now, section_texts_override)

    else:
        gaps = _detect_gaps_via_checklist(
            protocol, featured_only=True, section_texts_override=section_texts_override
        )

    return GapDetectionResponse(
        protocol_id=protocol_id,
        checklist_version=version,
        gaps_detected=gaps,
        detected_at=now,
    )


async def _detect_gaps_live(
    protocol_id: str,
    protocol: dict,
    now: datetime,
    section_texts_override: dict[str, str] | None = None,
) -> list[ProtocolGap]:
    """LIVE mode: deterministic checklist + LLM enrichment (up to 8 total)."""
    from app.utils.llm_mode_dependency import get_llm_client_for_mode

    client = get_llm_client_for_mode(LLMMode.LIVE)  # raises RuntimeError if no Azure creds

    # 1. Run deterministic detection first (all gaps, not just featured)
    checklist_gaps = _detect_gaps_via_checklist(
        protocol, featured_only=False, section_texts_override=section_texts_override
    )

    # 2. Build protocol text summary for the LLM
    sections_text = []
    for section in protocol.get("sections", []):
        heading = section.get("heading", "")
        text = " ".join(b.get("text", "") for b in section.get("blocks", []))
        sections_text.append(f"Section {section.get('number', '')}: {heading}\n{text[:500]}")
    protocol_summary = "\n\n".join(sections_text[:6])

    already_flagged = [g.name for g in checklist_gaps]

    prompt = f"""You are a senior medical writer reviewing a Phase III T2DM clinical trial protocol for completeness.

PROTOCOL EXCERPT:
{protocol_summary}

Already detected missing clauses: {json.dumps(already_flagged)}

Identify up to 3 ADDITIONAL gaps not in the already-detected list that a senior medical writer would expect to see in a complete Phase III T2DM protocol but are missing. Focus on regulatory-required or standard-of-care items only.

Return strictly JSON:
{{
  "additional_gaps": [
    {{
      "gap_id": "GAP_LLM_1",
      "name": "<gap name>",
      "category": "exclusion_criteria|inclusion_criteria|safety_reporting|other",
      "rationale": "<1-2 sentences>",
      "suggested_section": "<section name>",
      "suggested_section_id": "sec_4|sec_5|sec_6|sec_9",
      "draft_topic": "<topic for draft-clause endpoint>",
      "regulatory_reference": "<reference or null>",
      "severity": "standard"
    }}
  ]
}}
If no additional gaps, return {{"additional_gaps": []}}."""

    raw = await client.complete(prompt, agent="gap_detection")
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        llm_gaps_raw = data.get("additional_gaps", [])
        llm_gaps = [ProtocolGap(**g) for g in llm_gaps_raw if "gap_id" in g and "name" in g]
    except Exception:
        llm_gaps = []

    # Merge, dedupe by name, cap at 8
    all_names = {g.name for g in checklist_gaps}
    merged = list(checklist_gaps)
    for g in llm_gaps:
        if g.name not in all_names:
            merged.append(g)
            all_names.add(g.name)

    result = merged[:8]

    # Cache the result
    cache = _load_gap_cache()
    cache[_gap_cache_key(protocol_id)] = [g.model_dump() for g in result]
    _save_gap_cache(cache)

    return result
