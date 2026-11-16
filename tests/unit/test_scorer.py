"""
Unit tests for the reliability scorer.
"""
from decision_trace.quality.scorer import compute_reliability_score
from decision_trace.quality.rules import RULES


def test_all_rules_pass():
    report = compute_reliability_score([])
    assert report.overall_score == 100.0
    assert not report.capped
    assert report.failed_rule_names == []


def test_critical_failure_caps_score():
    # Pick a critical rule name
    critical_rules = [r for r in RULES if r.severity == "critical"]
    assert critical_rules, "No critical rules defined — check rules.py"
    failed = [critical_rules[0].rule_name]
    report = compute_reliability_score(failed)
    assert report.capped
    assert report.overall_score <= 60.0


def test_non_critical_failure_no_cap():
    info_rules = [r for r in RULES if r.severity == "info"]
    if not info_rules:
        return   # skip if no info rules
    failed = [info_rules[0].rule_name]
    report = compute_reliability_score(failed)
    assert not report.capped


def test_all_rules_fail():
    all_names = [r.rule_name for r in RULES]
    report = compute_reliability_score(all_names)
    assert report.overall_score == 0.0
    # overall_score is already 0, so capping at 60 has no visible effect;
    # only scores that *would* be above 60 are capped.
    # We just verify the score is at minimum.
    assert report.overall_score <= 60.0


def test_dimension_scores_populated():
    report = compute_reliability_score([])
    for dim in ["completeness", "uniqueness", "freshness", "validity"]:
        assert dim in report.dimensions
        assert report.dimensions[dim].score == 100.0
