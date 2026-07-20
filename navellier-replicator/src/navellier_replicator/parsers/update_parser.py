"""Update/article page parsing and the shared action classifier.

Update pages are prose, not tables, so extraction is keyword/phrase driven. The
:func:`classify_action` helper is shared with the portfolio parser so the
action taxonomy is defined in exactly one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from ..models.dto import ParsedItem
from ..models.enums import ConfidenceBand, ExtractionMethod, NormalizedAction
from . import PARSER_VERSION
from .confidence import ConfidenceInputs, band, score
from .ticker_utils import extract_tickers

# Ordered, most-specific-first. Each entry: (compiled regex, action, is_explicit).
# "explicit" means the phrase is unambiguous enough to boost confidence.
_ACTION_PATTERNS: list[tuple[re.Pattern[str], NormalizedAction, bool]] = [
    (re.compile(r"\badd(?:ing)?\s+more\b", re.I), NormalizedAction.ADD_MORE, True),
    (re.compile(r"\bbuy\s+more\b", re.I), NormalizedAction.ADD_MORE, True),
    (re.compile(r"\bincreas(?:e|ing)\s+(?:your\s+)?position\b", re.I), NormalizedAction.ADD_MORE, True),
    (re.compile(r"\bnew\s+buy\b", re.I), NormalizedAction.NEW_BUY, True),
    (re.compile(r"\bnew\s+recommendation\b", re.I), NormalizedAction.NEW_BUY, True),
    (re.compile(r"\binitiat(?:e|ing)\b", re.I), NormalizedAction.NEW_BUY, True),
    (re.compile(r"\btrim(?:ming)?\b", re.I), NormalizedAction.TRIM, True),
    (re.compile(r"\btake\s+partial\s+profits?\b", re.I), NormalizedAction.TRIM, True),
    (re.compile(r"\bsell\s+half\b", re.I), NormalizedAction.TRIM, True),
    (re.compile(r"\breduc(?:e|ing)\s+(?:your\s+)?position\b", re.I), NormalizedAction.TRIM, True),
    (re.compile(r"\bclos(?:e|ing|ed)\b", re.I), NormalizedAction.CLOSED, True),
    (re.compile(r"\bexit(?:ing)?\b", re.I), NormalizedAction.CLOSED, True),
    (re.compile(r"\bremov(?:e|ing|ed)\b", re.I), NormalizedAction.REMOVE, True),
    (re.compile(r"\bdelet(?:e|ing|ed)\b", re.I), NormalizedAction.REMOVE, True),
    (re.compile(r"\bsell\b", re.I), NormalizedAction.SELL, True),
    (re.compile(r"\bwatch\s*list\b", re.I), NormalizedAction.WATCHLIST, True),
    (re.compile(r"\bmonitor(?:ing)?\b", re.I), NormalizedAction.WATCHLIST, False),
    (re.compile(r"\bnew\s+position\b", re.I), NormalizedAction.NEW_BUY, True),
    (re.compile(r"\bbuy\s+below\b", re.I), NormalizedAction.ACTIVE_HOLD, True),
    (re.compile(r"\bhold(?:ing)?\b", re.I), NormalizedAction.ACTIVE_HOLD, True),
    (re.compile(r"\bmaintain\b", re.I), NormalizedAction.ACTIVE_HOLD, False),
    (re.compile(r"\bbuy\b", re.I), NormalizedAction.NEW_BUY, True),
]

# Actions grouped by lifecycle direction, used to detect conflicting signals.
_EXIT_ACTIONS = {NormalizedAction.SELL, NormalizedAction.REMOVE, NormalizedAction.CLOSED}
_ENTRY_ACTIONS = {NormalizedAction.NEW_BUY, NormalizedAction.ADD_MORE}


@dataclass
class ActionClassification:
    action: NormalizedAction
    explicit: bool
    matched: list[str] = field(default_factory=list)
    conflict: bool = False


def classify_action(text: str) -> ActionClassification:
    """Classify a text fragment into the normalized action taxonomy.

    Returns UNKNOWN when nothing matches. Sets ``conflict`` when both entry- and
    exit-type signals appear in the same fragment (which lowers confidence).
    """

    if not text:
        return ActionClassification(NormalizedAction.UNKNOWN, explicit=False)

    matches: list[tuple[NormalizedAction, bool, str]] = []
    for pattern, action, explicit in _ACTION_PATTERNS:
        m = pattern.search(text)
        if m:
            matches.append((action, explicit, m.group(0)))

    if not matches:
        return ActionClassification(NormalizedAction.UNKNOWN, explicit=False)

    # First match wins (patterns are ordered most-specific-first).
    chosen_action, chosen_explicit, _ = matches[0]
    distinct = {a for a, _, _ in matches}
    conflict = bool(distinct & _EXIT_ACTIONS) and bool(distinct & _ENTRY_ACTIONS)

    return ActionClassification(
        action=chosen_action,
        explicit=chosen_explicit,
        matched=[frag for _, _, frag in matches],
        conflict=conflict,
    )


def _sentences(text: str) -> list[str]:
    # Lightweight sentence split; good enough for signal localization.
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def parse_update_html(html: str, *, confidence_threshold: float) -> list[ParsedItem]:
    """Parse an update/article page into ParsedItems.

    Strategy: for each sentence containing a ticker, classify the action of that
    sentence. Sentences without a ticker are ignored. Every emitted item retains
    its source sentence for audit.
    """

    soup = BeautifulSoup(html or "", "lxml")
    text = soup.get_text(separator="\n")
    items: list[ParsedItem] = []
    seen: set[tuple[str, str]] = set()

    for sentence in _sentences(text):
        tickers = extract_tickers(sentence, allow_bare=True)
        if not tickers:
            continue
        cls = classify_action(sentence)
        cashtag = "$" in sentence
        for ticker in tickers:
            key = (ticker, cls.action.value)
            if key in seen:
                continue
            seen.add(key)

            ci = ConfidenceInputs(
                method=ExtractionMethod.KEYWORD,
                action=cls.action,
                cashtag_ticker=cashtag,
                explicit_action_phrase=cls.explicit,
                multiple_action_signals_conflict=cls.conflict,
            )
            conf = score(ci)
            items.append(
                ParsedItem(
                    ticker=ticker,
                    action=cls.action,
                    confidence=conf,
                    confidence_band=band(conf, confidence_threshold),
                    extraction_method=ExtractionMethod.KEYWORD,
                    source_snippet=sentence[:500],
                    parser_version=PARSER_VERSION,
                    notes={"components": str(ci.components), "matched": ",".join(cls.matched)},
                )
            )

    return items
