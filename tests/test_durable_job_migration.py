from __future__ import annotations

from pathlib import Path


def test_initial_durable_job_migration_defines_required_tables() -> None:
    migration = Path("migrations/0001_durable_job_state.sql")

    assert migration.exists()
    sql = migration.read_text()

    assert "CREATE SCHEMA IF NOT EXISTS open_swe" in sql
    assert "SET search_path TO open_swe" in sql
    assert "CREATE TABLE IF NOT EXISTS webhook_events" in sql
    assert "CREATE TABLE IF NOT EXISTS jobs" in sql
    assert "CREATE TABLE IF NOT EXISTS job_runs" in sql
    assert "CREATE TABLE IF NOT EXISTS integration_runs" in sql
    assert "uq_webhook_provider_event" in sql
    assert "REFERENCES jobs(id) ON DELETE CASCADE" in sql


def test_job_payload_migration_adds_payload_column() -> None:
    migration = Path("migrations/0002_job_payload_json.sql")

    assert migration.exists()
    sql = migration.read_text()

    assert "SET search_path TO open_swe" in sql
    assert "ALTER TABLE jobs" in sql
    assert "ADD COLUMN IF NOT EXISTS payload_json TEXT" in sql
