"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-25 06:20:29.404407+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "params", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('extraction', 'backtest', 'ocr', 'triage', 'ranking')", name="ck_eval_kind"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "institutions",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("sido", sa.String(length=32), nullable=False),
        sa.Column("sigungu", sa.String(length=32), nullable=True),
        sa.Column("region_code", sa.String(length=10), nullable=False),
        sa.Column("executive_code", sa.String(length=32), nullable=True),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.CheckConstraint(
            "kind IN ('local_gov', 'council', 'education_office', 'public_agency', 'central')",
            name="ck_institution_kind",
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(
        op.f("ix_institutions_region_code"), "institutions", ["region_code"], unique=False
    )
    op.create_table(
        "job_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("job", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "args", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'retrying')", name="ck_job_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_runs_failed",
        "job_runs",
        ["status"],
        unique=False,
        postgresql_where="status = 'failed'",
    )
    op.create_index("ix_job_runs_started", "job_runs", ["started_at"], unique=False)
    op.create_table(
        "llm_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(length=20), server_default="free", nullable=False),
        sa.Column("credit_balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("plan IN ('free', 'pro', 'team')", name="ck_org_plan"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "cursor", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_table(
        "alert_channels",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('email', 'slack', 'kakao')", name="ck_channel_kind"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alert_rules",
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("stages", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("quiet_start", sa.Integer(), nullable=False),
        sa.Column("quiet_end", sa.Integer(), nullable=False),
        sa.CheckConstraint("mode IN ('instant', 'daily', 'weekly')", name="ck_alert_mode"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id"),
    )
    op.create_table(
        "company_profiles",
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "exclude_keywords", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("region_codes", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("budget_min", sa.BigInteger(), nullable=True),
        sa.Column("budget_max", sa.BigInteger(), nullable=True),
        sa.Column("embedding", Vector(512), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("publisher_raw", sa.Text(), nullable=True),
        sa.Column("institution_code", sa.String(length=32), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("raw_uri", sa.Text(), nullable=True),
        sa.Column(
            "structured",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("text_quality", sa.Float(), nullable=True),
        sa.Column("parse_method", sa.String(length=32), nullable=True),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "doc_type IN ('council_minutes', 'budget_book', 'order_plan', 'prespec', 'bid_notice', 'award')",
            name="ck_document_type",
        ),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'parsed', 'failed', 'skipped')",
            name="ck_document_parse_status",
        ),
        sa.ForeignKeyConstraint(
            ["institution_code"],
            ["institutions.code"],
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_documents_source_external"),
    )
    op.create_index(
        "ix_documents_pending",
        "documents",
        ["parse_status"],
        unique=False,
        postgresql_where="parse_status = 'pending'",
    )
    op.create_index(
        "ix_documents_type_published", "documents", ["doc_type", "published_at"], unique=False
    )
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "stats", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'partial', 'failed')", name="ck_ingest_status"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingest_runs_source_started", "ingest_runs", ["source_id", "started_at"], unique=False
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("institution_code", sa.String(length=32), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.Date(), nullable=False),
        sa.Column("last_signal_at", sa.Date(), nullable=False),
        sa.Column("bid_window_start", sa.Date(), nullable=True),
        sa.Column("bid_window_end", sa.Date(), nullable=True),
        sa.Column("bid_published_at", sa.Date(), nullable=True),
        sa.Column("est_budget_krw", sa.BigInteger(), nullable=True),
        sa.Column("best_commitment", sa.String(length=16), nullable=True),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("conversion_prob", sa.Float(), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("embedding", Vector(512), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('council_mention', 'budget_line', 'order_plan', 'prespec', 'bid_notice', 'award')",
            name="ck_opportunity_stage",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'bid_open', 'closed', 'dormant')", name="ck_opportunity_status"
        ),
        sa.ForeignKeyConstraint(
            ["institution_code"],
            ["institutions.code"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunities_institution", "opportunities", ["institution_code"], unique=False
    )
    op.create_index(
        "ix_opportunities_status_window",
        "opportunities",
        ["status", "bid_window_start"],
        unique=False,
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("order_name", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("provider_payment_key", sa.String(length=200), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column(
            "raw", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('subscription', 'credit_pack')", name="ck_payment_kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'canceled')", name="ck_payment_status"
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("customer_key", sa.String(length=64), nullable=False),
        sa.Column("billing_key_enc", sa.Text(), nullable=True),
        sa.Column("card_summary", sa.String(length=64), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_charge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("plan IN ('free', 'pro', 'team')", name="ck_subscription_plan"),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled')",
            name="ck_subscription_status",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id"),
        sa.UniqueConstraint("customer_key"),
    )
    op.create_index(
        "ix_subscriptions_due", "subscriptions", ["status", "next_charge_at"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="owner", nullable=False),
        sa.Column("is_staff", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_user_role"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "briefs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("credits_spent", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_briefs_org_opportunity", "briefs", ["org_id", "opportunity_id"], unique=False
    )
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reason IN ('plan_grant', 'purchase', 'brief', 'refund', 'adjustment', 'expiry')",
            name="ck_ledger_reason",
        ),
        sa.CheckConstraint("balance_after >= 0", name="ck_ledger_non_negative"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_credit_ledger_org_created", "credit_ledger", ["org_id", "created_at"], unique=False
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("labels", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("triage_score", sa.Float(), nullable=True),
        sa.Column("triage_passed", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "seq", name="uq_chunk_doc_seq"),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("served_by", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'refusal', 'cache_hit', 'budget_skip', 'invalid_output')",
            name="ck_llm_status",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_calls_created", "llm_calls", ["created_at"], unique=False)
    op.create_index("ix_llm_calls_task_created", "llm_calls", ["task", "created_at"], unique=False)
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')", name="ck_notification_status"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["alert_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_notifications_pending", "notifications", ["status", "scheduled_at"], unique=False
    )
    op.create_table(
        "recommendations",
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ranker_version", sa.String(length=32), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("notified_stage", sa.String(length=32), nullable=True),
        sa.Column("feedback", sa.String(length=16), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "feedback IN ('relevant', 'irrelevant', 'won', 'dismissed')",
            name="ck_recommendation_feedback",
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("org_id", "opportunity_id"),
    )
    op.create_index(
        "ix_recommendations_org_score", "recommendations", ["org_id", "score"], unique=False
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("institution_code", sa.String(length=32), nullable=True),
        sa.Column("speaker_institution_code", sa.String(length=32), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("budget_krw", sa.BigInteger(), nullable=True),
        sa.Column("expected_year", sa.Integer(), nullable=True),
        sa.Column("expected_half", sa.String(length=2), nullable=True),
        sa.Column("commitment", sa.String(length=16), nullable=True),
        sa.Column("procurement_type", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "evidence", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "grounding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("extractor", sa.String(length=100), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=False),
        sa.Column(
            "external_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("embedding", Vector(512), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stage IN ('council_mention', 'budget_line', 'order_plan', 'prespec', 'bid_notice', 'award')",
            name="ck_signal_stage",
        ),
        sa.CheckConstraint(
            "verdict IN ('accepted', 'needs_review', 'rejected')", name="ck_signal_verdict"
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["institution_code"],
            ["institutions.code"],
        ),
        sa.ForeignKeyConstraint(
            ["speaker_institution_code"],
            ["institutions.code"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_signals_institution_observed",
        "signals",
        ["institution_code", "observed_at"],
        unique=False,
    )
    op.create_index("ix_signals_verdict", "signals", ["verdict"], unique=False)
    op.create_table(
        "opportunity_signals",
        sa.Column("opportunity_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("tentative", sa.Boolean(), nullable=False),
        sa.Column(
            "reasons", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "method IN ('ref', 'similarity', 'seed', 'manual')", name="ck_link_method"
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("opportunity_id", "signal_id"),
        sa.UniqueConstraint("signal_id"),
    )
    op.create_table(
        "review_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "resolution",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("resolved_by", sa.BigInteger(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'approved', 'edited', 'rejected')", name="ck_review_status"
        ),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id"),
    )

    # Approximate-NN search for linking (signal -> opportunity) and recommendation
    # (profile -> opportunity). HNSW over IVFFlat: no training step, good recall on a table that
    # grows every night, and Cloud SQL for PostgreSQL 16 supports it.
    for table in ("signals", "opportunities"):
        op.execute(
            f"CREATE INDEX ix_{table}_embedding_hnsw ON {table} "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
        )
    # Korean has no built-in text-search parser; trigram GIN indexes make ILIKE/similarity
    # keyword matching index-backed without a custom extension (see ADR-0004).
    op.execute(
        "CREATE INDEX ix_opportunities_title_trgm ON opportunities USING gin (title gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_signals_title_trgm ON signals USING gin (title gin_trgm_ops)")
    op.execute("CREATE INDEX ix_documents_title_trgm ON documents USING gin (title gin_trgm_ops)")


def downgrade() -> None:
    op.drop_table("review_items")
    op.drop_table("opportunity_signals")
    op.drop_index("ix_signals_verdict", table_name="signals")
    op.drop_index("ix_signals_institution_observed", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_recommendations_org_score", table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index("ix_notifications_pending", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_llm_calls_task_created", table_name="llm_calls")
    op.drop_index("ix_llm_calls_created", table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_table("document_chunks")
    op.drop_index("ix_credit_ledger_org_created", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_index("ix_briefs_org_opportunity", table_name="briefs")
    op.drop_table("briefs")
    op.drop_table("users")
    op.drop_index("ix_subscriptions_due", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("payments")
    op.drop_index("ix_opportunities_status_window", table_name="opportunities")
    op.drop_index("ix_opportunities_institution", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_ingest_runs_source_started", table_name="ingest_runs")
    op.drop_table("ingest_runs")
    op.drop_index("ix_documents_type_published", table_name="documents")
    op.drop_index(
        "ix_documents_pending", table_name="documents", postgresql_where="parse_status = 'pending'"
    )
    op.drop_table("documents")
    op.drop_table("company_profiles")
    op.drop_table("alert_rules")
    op.drop_table("alert_channels")
    op.drop_table("sources")
    op.drop_table("organizations")
    op.drop_table("llm_cache")
    op.drop_index("ix_job_runs_started", table_name="job_runs")
    op.drop_index("ix_job_runs_failed", table_name="job_runs", postgresql_where="status = 'failed'")
    op.drop_table("job_runs")
    op.drop_index(op.f("ix_institutions_region_code"), table_name="institutions")
    op.drop_table("institutions")
    op.drop_table("eval_runs")
