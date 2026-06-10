from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from control_plane.probe_postgres_queue import _dsn_from_env, _redact, _with_connect_timeout


class ControlPlanePostgresProbeTests(unittest.TestCase):
    def test_dsn_from_env_uses_host_override_and_timeout(self) -> None:
        dsn = _dsn_from_env(
            {
                "PGHOST": "localhost",
                "PGPORT": "5432",
                "PGDATABASE": "ragkb",
                "PGUSER": "ragkb",
                "PGPASSWORD": "secret value",
            },
            host_override="127.0.0.1",
            connect_timeout=3,
        )

        self.assertIn("@127.0.0.1:5432/ragkb", dsn)
        self.assertIn("connect_timeout=3", dsn)
        self.assertIn("secret%20value", dsn)

    def test_with_connect_timeout_does_not_duplicate_existing_timeout(self) -> None:
        dsn = _with_connect_timeout("postgresql://u:p@localhost:5432/db?connect_timeout=2", 5)

        self.assertEqual(dsn.count("connect_timeout="), 1)
        self.assertIn("connect_timeout=2", dsn)

    def test_redact_masks_plain_and_url_encoded_secrets(self) -> None:
        message = "failed for password secret value and secret%20value"

        self.assertEqual(_redact(message, ["secret value"]), "failed for password *** and ***")


if __name__ == "__main__":
    unittest.main()
