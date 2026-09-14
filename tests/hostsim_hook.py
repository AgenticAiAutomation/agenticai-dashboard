"""Example of BACKLINK_OPS_USER_HOOK — the recommended way to wire identity.

On the real dashboard this returns whatever your existing dependency returns
(the SQLAlchemy User row, or the pydantic model your get_current_user yields).
Anything with email / name / role works.
"""
from tests.hostsim import USERS


def get_user(request):
    return USERS.get(request.headers.get("x-hook-user"))
