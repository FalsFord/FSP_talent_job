"""Идемпотентные патчи схемы для БД, созданных предыдущей версией (create_all не меняет существующие таблицы).
На чистой БД все операторы — no-op. Для production рекомендуется перейти на Alembic-миграции."""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger("db.patches")

COLUMN_PATCHES = [
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS purpose VARCHAR(16) DEFAULT 'onboarding'",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS deadline_at TIMESTAMPTZ",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS time_limit_s INTEGER",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS scaled_score DOUBLE PRECISION",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS result VARCHAR(16)",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS integrity JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS languages JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS decision JSONB",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS grade_confirmed_at TIMESTAMPTZ",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS grade_valid_until TIMESTAMPTZ",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS is_discoverable BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS last_test_ratio DOUBLE PRECISION",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS task_ratio DOUBLE PRECISION",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS last_micro_at TIMESTAMPTZ",
    "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS languages JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE candidate_skills ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS contact_method VARCHAR(256)",
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64)",
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS viewed_at TIMESTAMPTZ",
    "ALTER TABLE invitations ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ",
    "ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS trust_flags JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE applications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
]

# Enum-значения добавляются вне транзакции (AUTOCOMMIT).
ENUM_PATCHES = [
    "ALTER TYPE invitationstatus ADD VALUE IF NOT EXISTS 'withdrawn'",
    "ALTER TYPE invitationstatus ADD VALUE IF NOT EXISTS 'expired'",
]

INDEX_PATCHES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_invitations_idem ON invitations (employer_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_invitations_candidate_status ON invitations (candidate_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_fts ON knowledge_chunks USING gin (to_tsvector('simple', text))",
    "CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS ix_candidates_embedding ON candidate_profiles USING hnsw (embedding vector_cosine_ops)",
]


async def apply_patches(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for stmt in [*COLUMN_PATCHES, *ENUM_PATCHES, *INDEX_PATCHES]:
            try:
                await conn.execute(text(stmt))
            except Exception as e:  # noqa: BLE001  (например, старый pgvector без HNSW — не критично)
                log.warning("schema patch skipped: %s (%s)", stmt[:70], str(e).splitlines()[0])
