from typing import Dict


def risk_to_color(score: float) -> str:
    if score <= 0.25:
        return "green"
    if score <= 0.5:
        return "yellow"
    if score <= 0.75:
        return "orange"
    return "red"


def risk_scores_to_buckets(scores: Dict[str, float]) -> Dict[str, str]:
    return {key: risk_to_color(float(value or 0.0)) for key, value in scores.items()}
