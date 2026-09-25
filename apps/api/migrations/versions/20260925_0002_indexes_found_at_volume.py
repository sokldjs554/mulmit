"""Indexes found by ``manage bench`` at production-like volume (docs/performance.md).

Measured on 100k opportunities / 400k signals:

* ``ix_opportunities_open_embedding_hnsw`` — the recommender asks for the 300 *open*
  opportunities nearest a company profile. On the full-table HNSW index pgvector applies the
  ``status`` filter after the index scan, which yields at most ``hnsw.ef_search`` rows: 13 of 300
  came back (recall 4 %). A partial index over open opportunities filters inside the index.
* ``ix_signals_external_refs_gin`` — linking by 발주계획/사전규격 number (``external_refs @>``)
  scanned every signal: 87 ms per lookup, up to three lookups per incoming procurement record.
* ``ix_opportunities_keywords_gin`` — keyword candidates now use ``keywords @> ARRAY[...]``,
  which a GIN index can serve (``= ANY(keywords)`` cannot use any index).
* Drops the full-table HNSW indexes on opportunities and signals. No query orders by them any
  more, and linking must stay exact (btree on institution + sort): an approximate index the
  planner might choose there would silently drop candidates. They also cost a graph update on
  every embedding write.

Everything runs CONCURRENTLY so a deploy never blocks writes on live tables.
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_open_embedding_hnsw "
            "ON opportunities USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64) WHERE status IN ('open', 'bid_open')"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_keywords_gin "
            "ON opportunities USING gin (keywords)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_signals_external_refs_gin "
            "ON signals USING gin (external_refs jsonb_path_ops)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_opportunities_embedding_hnsw")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signals_embedding_hnsw")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for table in ("opportunities", "signals"):
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_{table}_embedding_hnsw ON {table} "
                "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
            )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_signals_external_refs_gin")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_opportunities_keywords_gin")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_opportunities_open_embedding_hnsw")
