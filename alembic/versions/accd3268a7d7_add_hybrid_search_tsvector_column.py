"""add hybrid search tsvector column

Revision ID: accd3268a7d7
Revises: 19196fe163e5
Create Date: 2026-09-25 08:20:54.209544

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'accd3268a7d7'
down_revision: Union[str, None] = '19196fe163e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chunks', sa.Column('content_tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', content)", persisted=True), nullable=True))
    # NOTE: autogenerate incorrectly wanted to drop ix_chunks_embedding_cosine
    # here — it doesn't track that index because it was created with raw SQL
    # (op.execute), not declared via SQLAlchemy's Index(). That drop_index
    # call has been removed; the HNSW index is untouched by this migration.
    op.execute(
        "CREATE INDEX ix_chunks_content_tsv ON chunks USING gin (content_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.drop_column('chunks', 'content_tsv')
