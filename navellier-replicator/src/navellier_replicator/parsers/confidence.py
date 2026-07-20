"""Confidence scoring for extracted items.

Confidence is a transparent, additive score in [0, 1] built from named signals
so that a human can read *why* an item scored the way it did (the components are
kept in the item's ``notes``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.enums import ConfidenceBand, ExtractionMethod, NormalizedAction

# Base confidence per extraction method.
_METHOD_BASE = {
    ExtractionMethod.STRUCTURED_TABLE: 0.55,
    ExtractionMethod.KEYWORD: 0.45,
    ExtractionMethod.TEXT_FALLBACK: 0.30,
}


@dataclass
class ConfidenceInputs:
    method: ExtractionMethod
    action: NormalizedAction
    cashtag_ticker: bool = False          # ticker came from a $CASHTAG / exchange qualifier
    explicit_action_phrase: bool = False  # an unambiguous phrase like "Sell" / "Buy Below"
    has_company_name: bool = False
    ticker_in_dedicated_column: bool = False
    multiple_action_signals_conflict: bool = False
    components: dict[str, float] = field(default_factory=dict)


def score(inputs: ConfidenceInputs) -> float:
    """Compute an additive confidence score and record its components."""

    comp = inputs.components
    total = _METHOD_BASE.get(inputs.method, 0.30)
    comp["method_base"] = round(total, 3)

    def add(name: str, value: float) -> None:
        nonlocal total
        total += value
        comp[name] = round(value, 3)

    if inputs.cashtag_ticker:
        add("cashtag_ticker", 0.15)
    if inputs.ticker_in_dedicated_column:
        add("ticker_column", 0.10)
    if inputs.explicit_action_phrase:
        add("explicit_action", 0.20)
    if inputs.has_company_name:
        add("company_name", 0.05)
    if inputs.action is NormalizedAction.UNKNOWN:
        add("unknown_penalty", -0.25)
    if inputs.multiple_action_signals_conflict:
        add("conflict_penalty", -0.20)

    total = max(0.0, min(1.0, total))
    comp["total"] = round(total, 3)
    return total


def band(score_value: float, threshold: float) -> ConfidenceBand:
    return ConfidenceBand.from_score(score_value, threshold)
