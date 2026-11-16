"""
Reliability scorer.

Computes a 0–100 score per dimension and an overall composite score.
Critical failures cap the overall score at 60 regardless of other dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass

from decision_trace.quality.rules import RULES, Dimension, QualityRule


@dataclass
class DimensionScore:
    dimension: Dimension
    total_rules: int
    failed_rules: int
    critical_failures: int
    score: float          # 0–100


@dataclass
class ReliabilityReport:
    overall_score: float
    capped: bool          # True if critical failures reduced the score
    dimensions: dict[Dimension, DimensionScore]
    failed_rule_names: list[str]


def compute_reliability_score(failed_rule_names: list[str]) -> ReliabilityReport:
    """
    Given a list of rule names that failed, compute a ReliabilityReport.

    Parameters
    ----------
    failed_rule_names:
        Names of QualityRules that returned at least one violation.
    """
    failed_set = set(failed_rule_names)

    dim_data: dict[Dimension, dict] = {}
    for rule in RULES:
        d = rule.dimension
        if d not in dim_data:
            dim_data[d] = {"total": 0, "failed": 0, "critical": 0}
        dim_data[d]["total"] += 1
        if rule.rule_name in failed_set:
            dim_data[d]["failed"] += 1
            if rule.severity == "critical":
                dim_data[d]["critical"] += 1

    dimensions: dict[Dimension, DimensionScore] = {}
    for d, counts in dim_data.items():
        pass_rate = 1 - (counts["failed"] / counts["total"]) if counts["total"] else 1.0
        score = round(pass_rate * 100, 2)
        dimensions[d] = DimensionScore(
            dimension=d,
            total_rules=counts["total"],
            failed_rules=counts["failed"],
            critical_failures=counts["critical"],
            score=score,
        )

    # Weighted average: completeness 35%, uniqueness 30%, freshness 20%, validity 15%
    weights: dict[Dimension, float] = {
        "completeness": 0.35,
        "uniqueness":   0.30,
        "freshness":    0.20,
        "validity":     0.15,
    }
    weighted = sum(
        dimensions[d].score * weights.get(d, 0.0)
        for d in dimensions
    )
    overall = round(weighted, 2)

    # Cap at 60 if any critical failures exist
    total_critical = sum(ds.critical_failures for ds in dimensions.values())
    capped = False
    if total_critical > 0 and overall > 60:
        overall = 60.0
        capped = True

    return ReliabilityReport(
        overall_score=overall,
        capped=capped,
        dimensions=dimensions,
        failed_rule_names=list(failed_set),
    )
