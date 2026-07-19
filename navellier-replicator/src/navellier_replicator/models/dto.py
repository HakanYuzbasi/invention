"""Pydantic DTOs used to move data between pipeline stages.

These are the in-memory contracts; the ORM (``orm.py``) is the persistence
contract. Keeping them separate means parser upgrades and schema evolution stay
decoupled.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from .enums import (
    AuditFlagType,
    ConfidenceBand,
    ExtractionMethod,
    NormalizedAction,
    PageCategory,
    Severity,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PageCapture(BaseModel):
    """A single captured page plus its forensic metadata."""

    category: PageCategory
    requested_url: str
    final_url: str
    http_ok: bool
    html: str
    visible_text: str
    screenshot_path: str | None = None
    content_sha256: str
    captured_at: datetime = Field(default_factory=_utcnow)
    error: str | None = None

    @property
    def content_len(self) -> int:
        return len(self.visible_text or "")


class ParsedItem(BaseModel):
    """One normalized item extracted from a page."""

    ticker: str
    company_name: str | None = None
    action: NormalizedAction
    confidence: float
    confidence_band: ConfidenceBand
    extraction_method: ExtractionMethod
    source_snippet: str
    parser_version: str
    # Free-form extraction signals kept for audit (e.g. matched keywords).
    notes: dict[str, str] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _range(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def is_actionable(self) -> bool:
        return self.action.is_actionable


class ParseResult(BaseModel):
    """Everything a parser produced for one raw page."""

    raw_page_id: int
    parser_version: str
    items: list[ParsedItem] = Field(default_factory=list)
    parsed_at: datetime = Field(default_factory=_utcnow)

    @property
    def actionable_count(self) -> int:
        return sum(1 for it in self.items if it.is_actionable)


class AuditFlag(BaseModel):
    """A raised safety/audit condition."""

    flag_type: AuditFlagType
    severity: Severity
    message: str
    context: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class SafetyResult(BaseModel):
    """Outcome of running a set of guards."""

    passed: bool
    flags: list[AuditFlag] = Field(default_factory=list)

    @property
    def blocking_flags(self) -> list[AuditFlag]:
        return [f for f in self.flags if f.severity == Severity.BLOCK]

    def merge(self, other: "SafetyResult") -> "SafetyResult":
        return SafetyResult(
            passed=self.passed and other.passed,
            flags=[*self.flags, *other.flags],
        )


class ScrapeResult(BaseModel):
    """Summary of a scrape run passed back to the CLI/report."""

    run_id: int
    status: str
    pages: list[PageCapture] = Field(default_factory=list)
    safety: SafetyResult
