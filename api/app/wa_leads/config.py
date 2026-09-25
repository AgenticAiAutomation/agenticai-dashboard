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

def _roles(name: str, default: str) -> tuple[str, ...]:
    return tuple(r.strip() for r in os.environ.get(name, default).split(",") if r.strip())


# Who may open the desk at all. Owner only, by decision: this table holds every
# enquirer's phone number, email and what they said about their own business,
# which is commercially sensitive in a way the SEO screens are not. The SEO
# associates who use the rest of the dashboard have no reason to read it.
#
# To let a wider group in, add roles here rather than editing code:
#   Environment="WA_LEADS_READ_ROLES=owner,admin"
READ_ROLES = _roles("WA_LEADS_READ_ROLES", "owner")

# Who may move a lead through the pipeline. A subset of READ_ROLES in practice;
# a role that cannot read cannot write either, because the read gate runs first.
WRITE_ROLES = _roles("WA_LEADS_WRITE_ROLES", "owner")

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
