"""
6-factor weighted scoring engine + fake-mode scoring (scripted + heuristic).
"""
import json
import pathlib
import re
from typing import Any

import yaml

DATA_DIR = pathlib.Path(__file__).parent.parent / "data"

FACTOR_WEIGHTS: dict[str, float] = {
    "pattern_match_strength": 0.35,
    "therapeutic_area_fit": 0.20,
    "operational_complexity": 0.15,
    "inclusion_restrictiveness": 0.15,
    "endpoint_instrument_validation": 0.10,
    "visit_burden": 0.05,
}

# Country → primary required language
_COUNTRY_LANG: dict[str, str] = {
    "US": "en", "DE": "de", "FR": "fr", "JP": "ja",
    "BR": "pt", "CN": "zh", "ES": "es", "IT": "it",
    "KR": "ko", "NL": "nl",
}

DEMO_PROTOCOL_COUNTRIES = ["US", "DE", "FR", "JP", "BR", "CN"]


# ── Instruments ────────────────────────────────────────────────────────────────

def _load_instruments() -> list[dict]:
    with open(DATA_DIR / "instruments.yaml") as f:
        return yaml.safe_load(f)


_INSTRUMENTS: list[dict] = _load_instruments()

# Maps instrument_id and name fragments → instrument dict
_INSTRUMENT_INDEX: dict[str, dict] = {}
for _inst in _INSTRUMENTS:
    _INSTRUMENT_INDEX[_inst["instrument_id"].lower()] = _inst
    # Index each significant word of the name
    for _word in _inst["name"].lower().split():
        if len(_word) > 4:
            _INSTRUMENT_INDEX.setdefault(_word, _inst)


# ── Scripted demo scores ───────────────────────────────────────────────────────

def _load_demo_scores() -> dict[str, Any]:
    raw = json.loads((DATA_DIR / "demo_clause_scores.json").read_text())
    # strip metadata keys
    return {k: v for k, v in raw.items() if not k.startswith("_")}


_DEMO_SCORES: dict[str, Any] = _load_demo_scores()


# ── Core math ──────────────────────────────────────────────────────────────────

def compute_weighted_risk(factors: dict[str, int]) -> int:
    """Weighted sum of factor scores → 0-100 final risk score."""
    total = sum(factors[name] * weight for name, weight in FACTOR_WEIGHTS.items())
    return max(0, min(100, round(total)))


def risk_level(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def compute_overall_risk(n_high: int, n_medium: int, n_low: int) -> int:
    """
    Count-based formula. LOW clauses are capped at 12 for the contribution term
    (they contribute ~1/3 point each, max 4 points total). This cap ensures that
    accepting HIGH fixes — which moves clauses into the LOW bucket — does not
    inflate the LOW contribution and corrupt the 73 → 19 demo arc.

    Verification:
      3H/5M/12L: round(54 + 15 + min(12,12)//3) = round(54+15+4) = 73
      2H/5M/13L: round(36 + 15 + min(13,12)//3) = round(36+15+4) = 55
      1H/5M/14L: round(18 + 15 + min(14,12)//3) = round(18+15+4) = 37
      0H/5M/15L: round( 0 + 15 + min(15,12)//3) = round( 0+15+4) = 19
    """
    low_contribution = min(n_low, 12) // 3
    return round(n_high * 18 + n_medium * 3 + low_contribution)


# ── Heuristic fallback ─────────────────────────────────────────────────────────

def _detect_instrument(text_lower: str) -> dict | None:
    """Find the best-matching instrument from the registry given clause text."""
    for key, inst in _INSTRUMENT_INDEX.items():
        if key in text_lower:
            return inst
    return None


def _heuristic_factors(
    text: str, target_countries: list[str] | None = None
) -> tuple[dict[str, int], str | None]:
    """
    Lightweight keyword/rule heuristic for scoring arbitrary clauses in fake/mock mode.
    Returns (factor_scores, matched_pattern_id_or_None).
    """
    tl = text.lower()
    countries = target_countries or DEMO_PROTOCOL_COUNTRIES
    required_langs = {_COUNTRY_LANG.get(c, "en") for c in countries}

    factors: dict[str, int] = {k: 10 for k in FACTOR_WEIGHTS}
    matched_pattern: str | None = None

    # ── Drug-naïve / restrictive inclusion ────────────────────────────────────
    restrictive = [
        "drug-naïve", "drug-naive", "treatment-naive", "treatment naïve",
        "no prior", "never received", "naive to all", "no previous",
        "exclusively", "must not have", "have never",
    ]
    if any(s in tl for s in restrictive):
        factors["inclusion_restrictiveness"] = min(100, factors["inclusion_restrictiveness"] + 70)
        factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 72)
        matched_pattern = "AMD_001"

    # ── BMI ───────────────────────────────────────────────────────────────────
    if "bmi" in tl or "body mass index" in tl:
        m = re.search(r"(\d{2})\s*kg", tl)
        if m and int(m.group(1)) <= 35:
            factors["inclusion_restrictiveness"] = max(factors["inclusion_restrictiveness"], 65)
            factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 68)
            matched_pattern = matched_pattern or "AMD_002"

    # ── Visit burden ──────────────────────────────────────────────────────────
    visit_signals = ["weekly", "every visit", "each visit", "daily diary", "every week", "biweekly"]
    if any(s in tl for s in visit_signals):
        bump = 70 if ("weekly" in tl and "24" in tl) else 50
        factors["visit_burden"] = min(100, factors["visit_burden"] + bump)
        factors["operational_complexity"] = min(100, factors["operational_complexity"] + 25)
        factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 75 if "weekly" in tl and "24" in tl else 55)
        matched_pattern = matched_pattern or ("AMD_031" if "weekly" in tl and "24" in tl else "AMD_033")

    # ── Visit window ──────────────────────────────────────────────────────────
    if "±3" in text or "+/- 3" in tl or "plus or minus 3" in tl:
        factors["visit_burden"] = min(100, factors["visit_burden"] + 55)
        factors["operational_complexity"] = min(100, factors["operational_complexity"] + 40)
        factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 68)
        matched_pattern = matched_pattern or "AMD_032"

    # ── Instrument / PRO validation ───────────────────────────────────────────
    pro_signals = ["questionnaire", "quality of life", "qol", " pro ", "epro", "patient-reported", "patient reported"]
    if any(s in tl for s in pro_signals):
        inst = _detect_instrument(tl)
        if inst:
            validated = set(inst.get("validated_languages", []))
            missing = required_langs - validated
            if missing:
                gap = min(100, len(missing) * 38 + 25)
                if "native language" in tl or "local language" in tl or "mother tongue" in tl:
                    gap = min(100, gap + 20)
                factors["endpoint_instrument_validation"] = gap
                factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 72)
                factors["operational_complexity"] = min(100, factors["operational_complexity"] + 20)
                # Instrument validation takes priority over visit-burden pattern match
                matched_pattern = "AMD_021"
        else:
            # Generic PRO without identified instrument
            if "native language" in tl or "local language" in tl:
                factors["endpoint_instrument_validation"] = max(factors["endpoint_instrument_validation"], 50)
                matched_pattern = matched_pattern or "AMD_022"

    # ── Hepatic ───────────────────────────────────────────────────────────────
    if ("alt" in tl or "ast" in tl or "transaminase" in tl or "hepatic" in tl) and ("uln" in tl or "upper limit" in tl):
        factors["inclusion_restrictiveness"] = max(factors["inclusion_restrictiveness"], 45)
        factors["pattern_match_strength"] = max(factors["pattern_match_strength"], 55)
        matched_pattern = matched_pattern or "AMD_011"

    return factors, matched_pattern


def score_clause_heuristic(
    block_id: str,
    text: str,
    target_countries: list[str] | None = None,
) -> dict:
    """Return a ClauseRiskResult-shaped dict using the heuristic scorer."""
    factors_raw, matched_pattern_id = _heuristic_factors(text, target_countries)
    score = compute_weighted_risk(factors_raw)
    level = risk_level(score)

    factor_objs = {k: {"score": v, "reasoning": _heuristic_reasoning(k, v, text)} for k, v in factors_raw.items()}

    top_match = None
    if matched_pattern_id:
        top_match = {
            "pattern_id": matched_pattern_id,
            "match_percent": factors_raw["pattern_match_strength"],
            "description": _pattern_description(matched_pattern_id),
        }

    return {
        "block_id": block_id,
        "score": score,
        "risk_level": level,
        "factors": factor_objs,
        "top_pattern_match": top_match,
        "summary": _heuristic_summary(level, factors_raw, text),
    }


def score_clause_fake(block_id: str, text: str, target_countries: list[str] | None = None) -> dict:
    """
    Fake-mode scoring: scripted result for known demo block_ids, heuristic for everything else.
    Returns a ClauseRiskResult-shaped dict.
    """
    if block_id in _DEMO_SCORES:
        entry = _DEMO_SCORES[block_id]
        return {
            "block_id": block_id,
            "score": entry["score"],
            "risk_level": entry["risk_level"],
            "factors": entry["factors"],
            "top_pattern_match": entry["top_pattern_match"],
            "summary": entry["summary"],
        }
    return score_clause_heuristic(block_id, text, target_countries)


# ── Helper strings ─────────────────────────────────────────────────────────────

_PATTERN_DESCRIPTIONS: dict[str, str] = {
    "AMD_001": "Inclusion too restrictive — drug-naïve requirement causing >70% screen failure",
    "AMD_002": "BMI threshold too restrictive — excludes majority of obese T2DM population",
    "AMD_011": "Hepatic exclusion threshold may be too conservative",
    "AMD_021": "PRO instrument not validated in all target country languages",
    "AMD_022": "PRO instrument version mismatch across countries",
    "AMD_031": "Visit schedule too burdensome — weekly visits cause excessive dropout",
    "AMD_032": "Visit window ±3 days too narrow for multinational trial",
    "AMD_033": "Daily check-in requirement adds unsustainable patient burden",
}


def _pattern_description(pid: str) -> str:
    return _PATTERN_DESCRIPTIONS.get(pid, f"Amendment pattern {pid}")


def _heuristic_reasoning(factor: str, score: int, text: str) -> str:
    tl = text.lower()
    if factor == "inclusion_restrictiveness" and score > 40:
        return "Clause contains restrictive language that may narrow the eligible population significantly."
    if factor == "visit_burden" and score > 40:
        return "Clause requires frequent or inflexible patient visits that may drive dropout."
    if factor == "endpoint_instrument_validation" and score > 30:
        return "PRO/QoL instrument referenced may lack validated translations for all target country languages."
    if factor == "pattern_match_strength" and score > 50:
        return "Text closely matches historical amendment patterns for this clause type."
    return "No significant risk signal detected for this factor."


def _heuristic_summary(level: str, factors: dict[str, int], text: str) -> str:
    tl = text.lower()
    if factors.get("endpoint_instrument_validation", 0) > 50:
        return "PRO instrument may lack validated translations for all target countries — validate before study start or substitute a globally-validated instrument."
    if factors.get("inclusion_restrictiveness", 0) > 60:
        return "Restrictive eligibility language risks high screen failure rates; consider widening the criterion."
    if factors.get("visit_burden", 0) > 60:
        return "High visit frequency or narrow scheduling windows will increase patient dropout risk."
    if level == "medium":
        return "Moderate amendment risk detected; review against historical patterns before finalizing."
    return "Low amendment risk; clause follows established protocol conventions."
