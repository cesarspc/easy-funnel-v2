"""Re-exports the shared `db` fixture and `requires_database` marker.

The actual fixture lives in `tests/conftest.py` (root) so it is visible to
every test module, not just `tests/db/`. This module is kept so existing
`from tests.db.conftest import requires_database` imports keep working.
"""

from __future__ import annotations

from tests.conftest import db, requires_database

__all__ = ["db", "requires_database"]
