"""Settings for the WhatsApp leads desk.

Read from plain os.environ rather than the dashboard's pydantic settings, for
the same reason backlink_ops does: the dashboard's own settings load from
api/.env and are never pushed into os.environ, so a module that wants its own
switches sets them in the systemd unit instead. See docs/RUNBOOK.md.
"""
import os

VERSION = "1.0.0"
LOG_PREFIX = "wa-leads"

# Off by default. A module that mounts itself without being asked is a module
# that can break a deploy nobody expected to touch it.
ENABLED = os.environ.get("WA_LEADS_ENABLED", "0") == "1"

# The funnel's SQLite file. Both services run as www-data on this box, so the
# dashboard can open it directly; there is no second copy of the leads and
# therefore nothing to keep in sync.
DB_PATH = os.environ.get("WA_LEADS_DB", "/var/www/wa-funnel/instance/leads.db")

API_PREFIX = os.environ.get("WA_LEADS_API_PREFIX", "/api/wa-leads")

# Who may move a lead through the pipeline. Reading is open to any signed-in
# dashboard user; writing is not, because a status is a commitment about a
# real person waiting for a reply.
WRITE_ROLES = tuple(
    r.strip()
    for r in os.environ.get("WA_LEADS_WRITE_ROLES", "admin,owner,seo_lead,seo").split(",")
    if r.strip()
)

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
