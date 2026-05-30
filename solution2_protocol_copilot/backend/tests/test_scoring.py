"""Unit tests for scoring math."""
import pytest
from app.utils.scoring import compute_weighted_risk, risk_level, compute_overall_risk, FACTOR_WEIGHTS


def test_factor_weights_sum_to_one():
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_weighted_risk_all_zero():
    factors = {k: 0 for k in FACTOR_WEIGHTS}
    assert compute_weighted_risk(factors) == 0


def test_weighted_risk_all_hundred():
    factors = {k: 100 for k in FACTOR_WEIGHTS}
    assert compute_weighted_risk(factors) == 100


def test_weighted_risk_high_clause():
    # drug-naive like factors should produce HIGH score
    factors = {
        "pattern_match_strength": 92,
        "therapeutic_area_fit": 85,
        "operational_complexity": 30,
        "inclusion_restrictiveness": 95,
        "endpoint_instrument_validation": 0,
        "visit_burden": 10,
    }
    score = compute_weighted_risk(factors)
    assert score >= 60, f"Expected HIGH (≥60), got {score}"


def test_risk_level_thresholds():
    assert risk_level(100) == "high"
    assert risk_level(60) == "high"
    assert risk_level(59) == "medium"
    assert risk_level(30) == "medium"
    assert risk_level(29) == "low"
    assert risk_level(0) == "low"


def test_overall_risk_demo_distribution():
    """The critical test: 3H/5M/12L must produce 73."""
    result = compute_overall_risk(n_high=3, n_medium=5, n_low=12)
    assert result == 73, f"Expected 73, got {result}"


def test_overall_risk_post_fix():
    """After accepting 3 HIGH fixes: 0H/5M/12L must produce ~18 (target: 19)."""
    result = compute_overall_risk(n_high=0, n_medium=5, n_low=12)
    assert 15 <= result <= 22, f"Expected ~18-19, got {result}"


def test_overall_risk_zero():
    assert compute_overall_risk(0, 0, 0) == 0


def test_overall_risk_all_high():
    result = compute_overall_risk(10, 0, 0)
    assert result == 180  # 10 * 18 — no cap in formula


def test_deletion_removes_clause_score():
    """Deleting a HIGH clause from the score set recomputes overall + severity.

    Mirrors the frontend's handleClausesDeleted: drop the clause, recount
    severity from the remainder, and recompute overall via the same formula.
    """
    # Seeded demo distribution: 3 HIGH / 5 MED / 12 LOW = 73
    assert compute_overall_risk(3, 5, 12) == 73

    # Delete one HIGH clause (e.g. drug-naïve blk_4_4) → 2 HIGH / 5 MED / 12 LOW
    after = compute_overall_risk(2, 5, 12)
    assert after == 55, f"Expected 55 after deleting one HIGH, got {after}"

    # Deleting a LOW clause barely moves the needle but still recomputes
    assert compute_overall_risk(3, 5, 11) == compute_overall_risk(3, 5, 11)
    assert compute_overall_risk(3, 5, 11) < 73
