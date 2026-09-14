"""Backlink Ops — who is this, and what may they do.

Framework-free. The adapters hand this module a plain dict extracted from
whatever the host application already authenticated; nothing here knows about
Flask, FastAPI, JWTs or cookies.

ROLE MAPPING — this is the whole policy, in one place:

    superuser   email listed in BACKLINK_OPS_SUPERUSERS
                (or host role in BACKLINK_OPS_SUPERUSER_ROLES, default: none)
                → approves links, sets the difficulty level, edits the team,
                  reads the audit trail, triggers backups

    admin       host role in BACKLINK_OPS_ADMIN_ROLES
                (default: admin, seo_lead, editor, member)
                → logs links, keyword lab, both sites, AI coach, scoreboard

    viewer      host role in BACKLINK_OPS_VIEWER_ROLES (default: viewer)
                → reads everything, writes nothing

The dashboard's existing roles (admin / seo_lead / viewer) therefore map
straight across with no changes to its users table: seo_lead and admin become
desk admins, viewer stays read-only, and Jai is superuser by email — so role
escalation needs server access, not a UI click.
"""
from .config import settings


def normalise(raw):
    """raw: {'id','name','email','role'|'roles'} from a host adapter, or None."""
    if not raw:
        return None
    email = str(raw.get("email") or "").strip().lower()
    name = (raw.get("name") or raw.get("username") or raw.get("full_name")
            or email or raw.get("id") or "user")
    host_roles = raw.get("roles") or ([raw.get("role")] if raw.get("role") else [])
    host_roles = [str(r).strip().lower() for r in host_roles if r]
    user = {"id": str(raw.get("id") or email or name),
            "name": str(name),
            "email": email,
            "hostRoles": host_roles}
    user["role"] = assign(user)
    return user


def assign(user):
    email, uname = user["email"], user["name"].lower()
    roles = set(user["hostRoles"])

    if email in settings.SUPERUSERS or uname in settings.SUPERUSERS:
        return "superuser"
    if roles & set(settings.SUPERUSER_ROLES):
        return "superuser"
    if roles & set(settings.VIEWER_ROLES):
        return "viewer"
    if roles & set(settings.ADMIN_ROLES):
        return "admin"
    # Authenticated by the host but carrying no role we recognise: the safe
    # default is read-only, never write access.
    return "admin" if not roles and settings.UNKNOWN_ROLE_IS_ADMIN else "viewer"


def can_write(user):
    return bool(user) and user["role"] in ("superuser", "admin")


def is_superuser(user):
    return bool(user) and user["role"] == "superuser"
