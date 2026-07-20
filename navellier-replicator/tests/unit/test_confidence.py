from __future__ import annotations

from navellier_replicator.models.enums import ConfidenceBand, ExtractionMethod, NormalizedAction
from navellier_replicator.parsers.confidence import ConfidenceInputs, band, score


def test_structured_beats_text_fallback():
    structured = score(ConfidenceInputs(
        method=ExtractionMethod.STRUCTURED_TABLE, action=NormalizedAction.NEW_BUY,
    ))
    fallback = score(ConfidenceInputs(
        method=ExtractionMethod.TEXT_FALLBACK, action=NormalizedAction.NEW_BUY,
    ))
    assert structured > fallback


def test_signals_increase_confidence():
    base = score(ConfidenceInputs(
        method=ExtractionMethod.STRUCTURED_TABLE, action=NormalizedAction.NEW_BUY,
    ))
    boosted = score(ConfidenceInputs(
        method=ExtractionMethod.STRUCTURED_TABLE, action=NormalizedAction.NEW_BUY,
        cashtag_ticker=True, explicit_action_phrase=True, ticker_in_dedicated_column=True,
    ))
    assert boosted > base


def test_unknown_and_conflict_penalized():
    clean = score(ConfidenceInputs(
        method=ExtractionMethod.KEYWORD, action=NormalizedAction.SELL, explicit_action_phrase=True,
    ))
    penalized = score(ConfidenceInputs(
        method=ExtractionMethod.KEYWORD, action=NormalizedAction.UNKNOWN,
        multiple_action_signals_conflict=True,
    ))
    assert penalized < clean


def test_score_bounded():
    s = score(ConfidenceInputs(
        method=ExtractionMethod.STRUCTURED_TABLE, action=NormalizedAction.NEW_BUY,
        cashtag_ticker=True, explicit_action_phrase=True, has_company_name=True,
        ticker_in_dedicated_column=True,
    ))
    assert 0.0 <= s <= 1.0


def test_band_thresholds():
    assert band(0.95, 0.6) is ConfidenceBand.HIGH
    assert band(0.65, 0.6) is ConfidenceBand.MEDIUM
    assert band(0.40, 0.6) is ConfidenceBand.LOW
