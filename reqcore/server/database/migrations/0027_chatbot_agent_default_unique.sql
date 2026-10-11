-- Migration: enforce single default chatbot agent per (organization, user).
--
-- The chatbot_agent table allows one "default" agent per user inside an
-- organisation (the agent pre-selected when starting a new conversation).
-- The application code clears any prior default before promoting a new one,
-- but this is racy under concurrent requests. This partial unique index
-- enforces the invariant at the DB layer: any concurrent transaction that
-- would create a second default row will fail with a unique-constraint
-- violation, preserving correctness even if application-level coordination
-- breaks down.

CREATE UNIQUE INDEX IF NOT EXISTS "chatbot_agent_default_per_user_idx"
  ON "chatbot_agent" ("organization_id", "user_id")
  WHERE "is_default" = true;
