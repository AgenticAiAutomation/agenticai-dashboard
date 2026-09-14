-- Backlink Ops · migration 001 · UP
--
-- You do not normally run this by hand: app/backlink_ops/store.py:init_db()
-- applies the identical schema idempotently at first boot. This file exists so
-- the schema is reviewable in a diff, and so a DBA can pre-create it or port it
-- to Postgres (see docs/SCALING.md).
--
-- EVERY object is prefixed bo_ and lives in the module's own SQLite file. This
-- migration must never be run against the main dashboard database.

CREATE TABLE IF NOT EXISTS bo_schema_version (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT);

CREATE TABLE IF NOT EXISTS bo_entries (
    id TEXT PRIMARY KEY, project TEXT NOT NULL, date TEXT NOT NULL, author TEXT NOT NULL,
    url TEXT NOT NULL, host TEXT NOT NULL, type TEXT NOT NULL,
    da REAL NOT NULL DEFAULT 0, spam REAL NOT NULL DEFAULT 0,
    follow TEXT NOT NULL DEFAULT 'unknown', target TEXT NOT NULL DEFAULT '',
    anchor TEXT NOT NULL DEFAULT '', kw TEXT NOT NULL DEFAULT '',
    relevant INTEGER NOT NULL DEFAULT 0, indexed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_bo_entries_pd ON bo_entries(project, date);
CREATE INDEX IF NOT EXISTS ix_bo_entries_author ON bo_entries(author, date);

CREATE TABLE IF NOT EXISTS bo_reviews (
    entry_id TEXT PRIMARY KEY, status TEXT NOT NULL, note TEXT,
    reviewer TEXT NOT NULL, reviewed_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS bo_queries (
    id TEXT PRIMARY KEY, project TEXT NOT NULL, date TEXT NOT NULL, author TEXT NOT NULL,
    kw TEXT NOT NULL, volume INTEGER, kd INTEGER, cpc TEXT, verdict TEXT, why TEXT,
    raw TEXT, source TEXT NOT NULL DEFAULT 'ubersuggest', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_bo_queries_pd ON bo_queries(project, date);

CREATE TABLE IF NOT EXISTS bo_bank (
    project TEXT NOT NULL, kw TEXT NOT NULL, volume INTEGER, kd INTEGER, cpc TEXT,
    verdict TEXT, why TEXT, target_page TEXT, anchors TEXT, link_plan TEXT,
    author TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (project, kw));

CREATE TABLE IF NOT EXISTS bo_coach (
    project TEXT NOT NULL, date TEXT NOT NULL, author TEXT NOT NULL,
    payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (project, date, author));

CREATE TABLE IF NOT EXISTS bo_config (
    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_by TEXT, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS bo_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    role TEXT NOT NULL, action TEXT NOT NULL, target TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_bo_audit_at ON bo_audit(at);

CREATE TABLE IF NOT EXISTS bo_ai_usage (
    date TEXT NOT NULL, kind TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (date, kind));

INSERT OR IGNORE INTO bo_schema_version(version, applied_at, note)
VALUES (1, datetime('now'), 'initial install');
