"""SQLAlchemy ORM models — the persistence schema.

Design principle: **parser upgrades must never erase historical evidence.**

* ``raw_pages`` stores the full HTML, visible text, screenshot path, content
  hash, and post-redirect final URL for every page ever visited.
* ``extracted_items`` are *append-only* and carry the ``parser_version`` that
  produced them plus the ``source_snippet`` they came from. Re-parsing with a
  newer parser inserts NEW rows; it never mutates or deletes old ones.
* ``recommendation_events`` is an append-only event log; current active state is
  derived from it (wired in v0.2), not stored as the only truth.

All the v0.3 broker tables (``orders_sent``, ``fills``, ``broker_positions``)
exist now so the schema is stable, but nothing writes to them in v0.1.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin


class ScrapeRun(Base, TimestampMixin):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    app_env: Mapped[str] = mapped_column(String(32), nullable=False, default="dev")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_dir: Mapped[str | None] = mapped_column(String(512))
    notes: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)

    raw_pages: Mapped[list["RawPage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    audit_flags: Mapped[list["AuditFlagRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RawPage(Base, TimestampMixin):
    __tablename__ = "raw_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    final_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    http_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    visible_text: Mapped[str] = mapped_column(Text, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(String(512))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_len: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    run: Mapped[ScrapeRun] = relationship(back_populates="raw_pages")
    extracted_items: Mapped[list["ExtractedItem"]] = relationship(
        back_populates="raw_page", cascade="all, delete-orphan"
    )


class ExtractedItem(Base, TimestampMixin):
    """Append-only. A (raw_page, parser_version) may yield many rows; a newer
    parser version inserts new rows rather than overwriting older evidence."""

    __tablename__ = "extracted_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_page_id: Mapped[int] = mapped_column(
        ForeignKey("raw_pages.id"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id"), nullable=False, index=True)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    company_name: Mapped[str | None] = mapped_column(String(256))
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(8), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(24), nullable=False)
    source_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    notes_json: Mapped[str | None] = mapped_column(Text)

    raw_page: Mapped[RawPage] = relationship(back_populates="extracted_items")


class RecommendationEvent(Base, TimestampMixin):
    """Append-only recommendation event log. Populated in v0.2; the table exists
    now so the schema is stable and migrations don't churn."""

    __tablename__ = "recommendation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_service: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extracted_item_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_items.id"))
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    __table_args__ = (
        # Prevent inserting the exact same observed event twice.
        UniqueConstraint("dedupe_key", name="uq_recommendation_events_dedupe_key"),
    )


class PortfolioTarget(Base, TimestampMixin):
    """A computed target holding for a given policy + as-of date (v0.2)."""

    __tablename__ = "portfolio_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_dollars: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class OrderSent(Base, TimestampMixin):
    """Order intents. In v0.1/v0.2 nothing writes here; in v0.3 PLANNED intents
    are persisted BEFORE any (paper-only) submission."""

    __tablename__ = "orders_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    policy: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="MKT")
    limit_price: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PLANNED")
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_orders_sent_idempotency_key"),
    )


class Fill(Base, TimestampMixin):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders_sent.id"), index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BrokerPosition(Base, TimestampMixin):
    __tablename__ = "broker_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost: Mapped[float | None] = mapped_column(Float)
    market_price: Mapped[float | None] = mapped_column(Float)
    market_value: Mapped[float | None] = mapped_column(Float)
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuditFlagRow(Base, TimestampMixin):
    __tablename__ = "audit_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_runs.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run: Mapped[ScrapeRun | None] = relationship(back_populates="audit_flags")


__all__ = [
    "ScrapeRun",
    "RawPage",
    "ExtractedItem",
    "RecommendationEvent",
    "PortfolioTarget",
    "OrderSent",
    "Fill",
    "BrokerPosition",
    "AuditFlagRow",
]
