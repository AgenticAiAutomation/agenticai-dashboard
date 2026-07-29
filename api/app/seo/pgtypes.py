"""Shared helper for binding Python enums to native Postgres enum types.

The migration owns creation of the types, so models must not try to emit
CREATE TYPE on table creation — hence create_type=False everywhere.
"""
from sqlalchemy.dialects.postgresql import ENUM

from app.seo.enums import PG_ENUM_NAMES


def pg_enum(python_enum):
    """Return a Postgres ENUM column type bound to `python_enum`."""
    return ENUM(
        *[member.value for member in python_enum],
        name=PG_ENUM_NAMES[python_enum],
        create_type=False,
    )
