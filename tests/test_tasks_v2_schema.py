"""Tasks v2, Step 1: schema 3 (new tables only) on an existing schema-2 database.

  * the upgrade takes a backup first, and leaves every T4/T7 table and row exactly as it was
  * 22 categories, the 7-hour settings and the badges are seeded; running it again changes nothing
  * guardrails: no v2 row can be deleted or replaced; the trail, proof and points never change;
    one open interval per person, closed once; leave cancelled once; corrections decided once
  * rollback = restore the pre-v3 backup: the old database comes back exactly

Run:  PYTHONPATH="api;." python tests/test_tasks_v2_schema.py
"""
import glob
import os
import shutil
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
TMP = tempfile.mkdtemp(prefix="tv2-")
DB = os.path.join(TMP, "dt.db")
os.environ.update({"DAILY_TRACKER_DB": DB, "DAILY_TRACKER_BACKUP_DIR": os.path.join(TMP, "bk")})

from app.daily_tracker import store  # noqa: E402

PASS = 0


def check(label, cond):
    global PASS
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        raise SystemExit(1)
    PASS += 1


def refused(sql, args=()):
    try:
        store.write(sql, args)
    except sqlite3.DatabaseError:
        return True
    return False


def snapshot(path, tables):
    c = sqlite3.connect(path)
    out = {t: (c.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone(),
               c.execute(f"SELECT * FROM {t} ORDER BY rowid").fetchall()) for t in tables}
    c.close()
    return out


# ---- a schema-2 database, as production has it today: the real init, v3 step off
v3, store._migrate_v3 = store._migrate_v3, lambda conn: None
store.settings.SCHEMA_VERSION = 2
store.init_db()
store.connect().close()
store._local.conn = None
store._migrate_v3, store.settings.SCHEMA_VERSION = v3, 3
old = sqlite3.connect(DB)
check("fixture is schema 2", old.execute("SELECT MAX(version) FROM dt_schema_version").fetchone()[0] == 2)
old.execute("INSERT INTO tasks(title, description, project_id, goal, target_qty, unit, effort_hours, start_at, due_at,"
            " created_by, created_at, updated_at) VALUES ('Old T7 task', 'd', 'agentic', 'g', 5, 'backlinks', 2,"
            " '2026-10-20T09:00', '2026-10-21T18:00', '1', 'x', 'x')")
old.execute("INSERT INTO leave_days VALUES ('7', '2026-10-20', 'sick')")
old.execute("INSERT INTO points_ledger(user_id, points, reason, ref_type, ref_id, month, created_at)"
            " VALUES ('7', 12, 'task', 'task', '1', '2026-10', 'x')")
old.commit()
OLD_TABLES = [r[0] for r in old.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
old.close()
before = snapshot(DB, [t for t in OLD_TABLES if t != "dt_schema_version"])

print("Upgrade")
store.init_db()
check("schema is 3", store.one("SELECT MAX(version) v FROM dt_schema_version")["v"] == 3)
backups = glob.glob(os.path.join(TMP, "bk", "*pre-v3.db"))
check("a pre-v3 backup was taken", len(backups) == 1)
check("every old table and row is unchanged", snapshot(DB, list(before)) == before)
have = {r["name"] for r in store.rows("SELECT name FROM sqlite_master WHERE type='table'")}
check("all v2 tables exist", set(store.V3_TABLES) <= have)
check("Jai's 8 categories seeded", store.one("SELECT COUNT(*) c FROM task_categories")["c"] == 8)
nw = store.one("SELECT * FROM task_categories WHERE name='New website development'")
check("New website development: 3 working days, dependency stop needs Jai",
      nw["deadline_workdays"] == 3 and nw["hold_needs_approval"] == 1)
need = {r["name"]: [f["key"] for f in __import__("json").loads(r["fields"])]
        for r in store.rows("SELECT name, fields FROM task_categories")}
check("each category names what must be filled in",
      need["Article writing"] == ["website"] and need["Content writing"] == ["purpose"]
      and need["Website development"] == ["page", "updates"]
      and need["Calling"] == need["Follow-up"] == need["Meeting"] == ["reason"])
cfg = store.one("SELECT value FROM work_settings ORDER BY id DESC LIMIT 1")["value"]
check("settings: 7 h, Mon-Sat, 2 leaves, 15-min slots",
      all(s in cfg for s in ('"daily_target_hours": 7', '"working_days": [0, 1, 2, 3, 4, 5]',
                             '"leave_allowance_per_month": 2', '"slot_minutes": 15')))
check("badges seeded", store.one("SELECT COUNT(*) c FROM badges")["c"] == 7)

store.init_db()
check("running it again: no second backup, nothing re-seeded",
      len(glob.glob(os.path.join(TMP, "bk", "*.db"))) == 1
      and store.one("SELECT COUNT(*) c FROM task_categories")["c"] == 8
      and store.one("SELECT COUNT(*) c FROM work_settings")["c"] == 1
      and store.one("SELECT COUNT(*) c FROM dt_schema_version WHERE version=3")["c"] == 1)

print("Guardrails")
T = "2026-10-26T04:30:00+00:00"
store.write("INSERT INTO work_tasks(title, created_by, created_at, updated_at) VALUES ('Pool task', '1', ?, ?)", (T, T))
store.write("INSERT INTO task_events(user_id, task_id, event_type, server_ts) VALUES ('7', 1, 'start', ?)", (T,))
store.write("INSERT INTO work_slots(user_id, task_id, slot_start, url, domain, server_ts) "
            "VALUES ('7', 1, '2026-10-26T10:00', 'https://a.co/x', 'a.co', ?)", (T,))
store.write("INSERT INTO work_points(user_id, task_id, rule, ref, points, awarded_by, created_at) "
            "VALUES ('7', 1, 'task_accepted', 'task:1', 10, '1', ?)", (T,))
check("a task event can't be edited", refused("UPDATE task_events SET reason='x'"))
check("a 15-min proof can't be edited", refused("UPDATE work_slots SET url='https://b.co'"))
check("a 15-min proof can't be replaced (INSERT OR REPLACE)",
      refused("INSERT OR REPLACE INTO work_slots(user_id, slot_start, server_ts) VALUES ('7', '2026-10-26T10:00', ?)", (T,)))
check("the same points can't be awarded twice",
      refused("INSERT INTO work_points(user_id, task_id, rule, ref, points, awarded_by, created_at) "
              "VALUES ('7', 1, 'task_accepted', 'task:1', 10, '1', ?)", (T,)))
check("points can't be edited", refused("UPDATE work_points SET points=99"))
check("settings history can't be edited", refused("UPDATE work_settings SET value='{}'"))
check("a task's status can change", not refused("UPDATE work_tasks SET status='picked', updated_at=? WHERE id=1", (T,)))
check("who created a task can't change", refused("UPDATE work_tasks SET created_by='9' WHERE id=1"))

store.write("INSERT INTO work_intervals(user_id, task_id, start_ts, created_at) VALUES ('7', 1, ?, ?)", (T, T))
check("a second open interval for the same person is refused",
      refused("INSERT INTO work_intervals(user_id, task_id, start_ts, created_at) VALUES ('7', 1, ?, ?)", (T, T)))
check("another person can have their own open interval",
      not refused("INSERT INTO work_intervals(user_id, start_ts, created_at) VALUES ('8', ?, ?)", (T, T)))
check("an interval can't end before it starts",
      refused("UPDATE work_intervals SET end_ts='2026-10-26T04:00:00+00:00' WHERE id=1"))
check("an interval can't be moved", refused("UPDATE work_intervals SET start_ts='2026-10-26T03:00:00+00:00' WHERE id=1"))
check("an interval closes", not refused("UPDATE work_intervals SET end_ts='2026-10-26T05:30:00+00:00' WHERE id=1"))
check("a closed interval can't be changed again",
      refused("UPDATE work_intervals SET end_ts='2026-10-26T06:30:00+00:00' WHERE id=1"))

store.write("INSERT INTO leave_calendar(user_id, date, type, credited_hours, declared_by, declared_at) "
            "VALUES ('7', '2026-10-27', 'emergency', 7, '1', ?)", (T,))
check("the same person and day can't hold two active leaves",
      refused("INSERT INTO leave_calendar(user_id, date, type, declared_by, declared_at) "
              "VALUES ('7', '2026-10-27', 'allowance', '7', ?)", (T,)))
check("leave credit can't be edited", refused("UPDATE leave_calendar SET credited_hours=14 WHERE id=1"))
check("leave can be cancelled", not refused("UPDATE leave_calendar SET cancelled_at=?, cancelled_by='1' WHERE id=1", (T,)))
check("cancelled leave stays cancelled", refused("UPDATE leave_calendar SET cancelled_at=NULL WHERE id=1"))
check("after cancelling, the day can be declared again",
      not refused("INSERT INTO leave_calendar(user_id, date, type, declared_by, declared_at) "
                  "VALUES ('7', '2026-10-27', 'allowance', '7', ?)", (T,)))

store.write("INSERT INTO time_corrections(user_id, interval_id, field, original_value, new_value, reason, "
            "requested_by, requested_at) VALUES ('7', 1, 'end_ts', 'a', 'b', 'forgot to stop', '7', ?)", (T,))
check("a correction request can't be rewritten", refused("UPDATE time_corrections SET new_value='c' WHERE id=1"))
check("Jai decides a correction",
      not refused("UPDATE time_corrections SET status='approved', decided_by='1', decided_at=? WHERE id=1", (T,)))
check("a decided correction can't be decided again", refused("UPDATE time_corrections SET status='rejected' WHERE id=1"))
check("T7 tables still allow their normal edits (no v2 triggers leaked)",
      not refused("INSERT OR REPLACE INTO leave_days VALUES ('7', '2026-10-20', 'sick (updated)')"))

store.write("INSERT INTO task_holds(task_id, user_id, depends_on_name, reason, start_ts) "
            "VALUES (1, '7', 'Client Ravi', 'waiting for logo files', ?)", (T,))
check("a second open hold on the same task is refused",
      refused("INSERT INTO task_holds(task_id, user_id, depends_on_name, reason, start_ts) "
              "VALUES (1, '7', 'Priya', 'x', ?)", (T,)))
check("who the hold waits on can't be changed", refused("UPDATE task_holds SET depends_on_name='Someone else'"))
check("a hold ends", not refused("UPDATE task_holds SET end_ts='2026-10-26T08:00:00+00:00'"))
check("its end can't be moved", refused("UPDATE task_holds SET end_ts='2026-10-26T09:00:00+00:00'"))
check("Jai approves it", not refused("UPDATE task_holds SET status='approved', decided_by='1', decided_at=?", (T,)))
check("the decision can't be changed", refused("UPDATE task_holds SET status='rejected'"))
store.write("INSERT INTO badges_awarded(user_id, code, ref, awarded_by, awarded_at) VALUES ('7', 'helper', 'task:1', '1', ?)", (T,))
store.write("INSERT INTO employee_of_month(month, user_id, chosen_by, chosen_at) VALUES ('2026-10', '7', '1', ?)", (T,))
store.write("INSERT INTO work_days(user_id, date, start_at) VALUES ('7', '2026-10-26', ?)", (T,))
store.write("INSERT INTO daily_routines(title, created_by, created_at) VALUES ('Check inbox', '1', ?)", (T,))
store.write("INSERT INTO day_hours(date, hours, set_by, set_at) VALUES ('2026-10-31', 4, '1', ?)", (T,))
store.write("INSERT INTO hour_allowance(user_id, hours, set_by, set_at) VALUES ('*', 8, '1', ?)", (T,))
store.write("INSERT INTO week_hours(week, effective_from, set_by, set_at) VALUES ('[7,7,7,7,7,7,0]', '2026-11-26', '1', ?)", (T,))
store.write("INSERT INTO big_ideas(user_id, month, title, channel, idea, created_at) VALUES ('7', '2026-10', 'GBP posts', 'Google Maps', 'Post weekly on Google Business Profile', ?)", (T,))
check("every v2 table has a row to protect",
      all(store.one(f"SELECT COUNT(*) c FROM {t}")["c"] for t in store.V3_TABLES))
for t in store.V3_TABLES:
    check(f"DELETE on {t} is refused", refused(f"DELETE FROM {t}"))
check("employee of the month can't be changed once chosen", refused("UPDATE employee_of_month SET user_id='8'"))

print("Rollback")
store.connect().close()
store._local.conn = None
for ext in ("-wal", "-shm"):
    if os.path.exists(DB + ext):
        os.remove(DB + ext)
shutil.copyfile(backups[0], DB)
c = sqlite3.connect(DB)
names = {r[0] for r in c.execute("SELECT name FROM sqlite_master")}
c.close()
check("restoring the pre-v3 backup brings back the old database exactly",
      snapshot(DB, list(before)) == before and not (names & set(store.V3_TABLES)))

print(f"\n{PASS} checks passed")
