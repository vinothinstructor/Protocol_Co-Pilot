"""Tests for fake-mode scripted scores and heuristic fallback."""
import pytest
from app.utils.scoring import score_clause_fake, score_clause_heuristic


def test_scripted_drug_naive():
    result = score_clause_fake(
        "blk_4_4",
        "Be drug-naïve at screening, with no prior antidiabetic agents of any kind.",
    )
    assert result["score"] == 88
    assert result["risk_level"] == "high"
    assert result["top_pattern_match"]["pattern_id"] == "AMD_001"


def test_scripted_bmi():
    result = score_clause_fake("blk_4_3", "Have a body mass index (BMI) below 35 kg/m².")
    assert result["score"] == 82
    assert result["risk_level"] == "high"
    assert result["top_pattern_match"]["pattern_id"] == "AMD_002"


def test_scripted_weekly_visits():
    result = score_clause_fake(
        "blk_6_2",
        "Participants must attend clinic weekly throughout the 24-week treatment period.",
    )
    assert result["score"] == 78
    assert result["risk_level"] == "high"
    assert result["top_pattern_match"]["pattern_id"] == "AMD_031"


def test_scripted_low_clause():
    result = score_clause_fake("blk_5_1", "Have a confirmed diagnosis of Type 1 Diabetes Mellitus.")
    assert result["score"] == 7
    assert result["risk_level"] == "low"
    assert result["top_pattern_match"] is None


def test_heuristic_drug_naive_signal():
    text = "Patients must be drug-naïve with no prior therapy of any kind."
    result = score_clause_heuristic("blk_unknown_1", text)
    assert result["risk_level"] in ("medium", "high")
    assert result["factors"]["inclusion_restrictiveness"]["score"] >= 60


def test_heuristic_weekly_visits():
    text = "Participants must attend clinic weekly for 24 weeks."
    result = score_clause_heuristic("blk_unknown_2", text)
    assert result["factors"]["visit_burden"]["score"] >= 60
    assert result["risk_level"] in ("medium", "high")


def test_heuristic_qol_mandarin():
    """The unrehearsed demo moment: QoL_12 + native language → MEDIUM citing validation gap."""
    text = (
        "Patient must complete the 12-item Quality-of-Life questionnaire "
        "in their native language at every visit."
    )
    result = score_clause_heuristic(
        "blk_unknown_99",
        text,
        target_countries=["US", "DE", "FR", "JP", "BR", "CN"],
    )
    # Should detect zh/pt validation gap → endpoint_instrument_validation raised
    assert result["factors"]["endpoint_instrument_validation"]["score"] >= 50, (
        f"Expected high instrument validation score, got {result['factors']['endpoint_instrument_validation']}"
    )
    assert result["risk_level"] == "medium", f"Expected medium, got {result['risk_level']}"
    # Pattern match should point to AMD_021
    assert result["top_pattern_match"] is not None
    assert result["top_pattern_match"]["pattern_id"] == "AMD_021"


def test_heuristic_standard_clause_low():
    text = "Participants must provide written informed consent before any study procedures."
    result = score_clause_heuristic("blk_unknown_3", text)
    assert result["risk_level"] == "low"


def test_unknown_block_id_uses_heuristic():
    text = "Be aged 25 to 55 years only."
    result = score_clause_fake("blk_nonexistent_999", text)
    # Should fall through to heuristic, not crash
    assert "score" in result
    assert "risk_level" in result
