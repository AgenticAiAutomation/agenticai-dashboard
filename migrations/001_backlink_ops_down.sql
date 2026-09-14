-- Backlink Ops · migration 001 · DOWN
--
-- DESTRUCTIVE. This erases every backlink, keyword verdict and approval the
-- team has logged. In almost every case you want the reversible rollback
-- instead: set BACKLINK_OPS_ENABLED=0 and restart. See docs/BCP_AND_ROLLBACK.md.
--
-- Take a backup first:  sqlite3 instance/backlink_ops.db ".backup 'pre-drop.db'"

DROP TABLE IF EXISTS bo_ai_usage;
DROP TABLE IF EXISTS bo_audit;
DROP TABLE IF EXISTS bo_config;
DROP TABLE IF EXISTS bo_coach;
DROP TABLE IF EXISTS bo_bank;
DROP TABLE IF EXISTS bo_queries;
DROP TABLE IF EXISTS bo_reviews;
DROP TABLE IF EXISTS bo_entries;
DROP TABLE IF EXISTS bo_schema_version;
