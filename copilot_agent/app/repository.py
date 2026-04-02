from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


@dataclass
class StoredRun:
    run_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    encounter_id: str
    status: str
    intent: str | None
    requires_human_review: bool
    patch_preview: dict[str, Any] | None
    final_response: str | None
    trace_metadata: dict[str, Any]


@dataclass
class StoredRunEvent:
    sequence: int
    event: str
    run_id: str
    thread_id: str
    created_at: datetime
    payload: dict[str, Any]


class CopilotRunRepository:
    def setup(self, conn: Connection) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS copilot_runs (
                    run_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    encounter_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    intent TEXT NULL,
                    requires_human_review BOOLEAN NOT NULL DEFAULT FALSE,
                    patch_preview JSONB NULL,
                    final_response TEXT NULL,
                    trace_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS copilot_run_events (
                    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES copilot_runs(run_id) ON DELETE CASCADE,
                    thread_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS copilot_run_events_run_sequence_idx
                ON copilot_run_events (run_id, sequence)
                """
            )

    def create_run(self, conn: Connection, *, run: StoredRun) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO copilot_runs (
                    run_id,
                    thread_id,
                    tenant_id,
                    user_id,
                    encounter_id,
                    status,
                    intent,
                    requires_human_review,
                    patch_preview,
                    final_response,
                    trace_metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                """,
                (
                    run.run_id,
                    run.thread_id,
                    run.tenant_id,
                    run.user_id,
                    run.encounter_id,
                    run.status,
                    run.intent,
                    run.requires_human_review,
                    json.dumps(run.patch_preview) if run.patch_preview else None,
                    run.final_response,
                    json.dumps(run.trace_metadata),
                ),
            )

    def update_run(self, conn: Connection, *, run: StoredRun) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE copilot_runs
                SET
                    status = %s,
                    intent = %s,
                    requires_human_review = %s,
                    patch_preview = %s::jsonb,
                    final_response = %s,
                    trace_metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE run_id = %s
                """,
                (
                    run.status,
                    run.intent,
                    run.requires_human_review,
                    json.dumps(run.patch_preview) if run.patch_preview else None,
                    run.final_response,
                    json.dumps(run.trace_metadata),
                    run.run_id,
                ),
            )

    def get_run(self, conn: Connection, run_id: str) -> StoredRun:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    run_id,
                    thread_id,
                    tenant_id,
                    user_id,
                    encounter_id,
                    status,
                    intent,
                    requires_human_review,
                    patch_preview,
                    final_response,
                    trace_metadata
                FROM copilot_runs
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise KeyError(run_id)

        return StoredRun(**row)

    def list_events(
        self, conn: Connection, run_id: str, *, after_sequence: int = 0
    ) -> list[StoredRunEvent]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sequence, event, run_id, thread_id, created_at, payload
                FROM copilot_run_events
                WHERE run_id = %s AND sequence > %s
                ORDER BY sequence ASC
                """,
                (run_id, after_sequence),
            )
            rows = cur.fetchall()

        return [StoredRunEvent(**row) for row in rows]

    def append_events(
        self,
        conn: Connection,
        *,
        run_id: str,
        thread_id: str,
        events: list[dict[str, Any]],
    ) -> list[StoredRunEvent]:
        stored_events: list[StoredRunEvent] = []

        with conn.cursor(row_factory=dict_row) as cur:
            for event in events:
                cur.execute(
                    """
                    INSERT INTO copilot_run_events (run_id, thread_id, event, payload)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING sequence, event, run_id, thread_id, created_at, payload
                    """,
                    (
                        run_id,
                        thread_id,
                        event["event"],
                        json.dumps(event["payload"]),
                    ),
                )
                stored_events.append(StoredRunEvent(**cur.fetchone()))

        return stored_events

