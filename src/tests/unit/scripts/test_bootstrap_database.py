"""Bootstrap distinguishes a missing database from unrelated connection failures."""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import psycopg

from scripts.bootstrap_database import ensure_database

URL = "postgresql://operator:synthetic-password@localhost:5432/test_db"


class BootstrapTests(TestCase):
    def test_existing_database_is_only_checked(self):
        with patch("scripts.bootstrap_database.psycopg.connect") as connect:
            self.assertFalse(ensure_database(URL))
            connect.assert_called_once_with(URL, connect_timeout=5)

    def test_unrelated_failures_never_trigger_creation(self):
        for error in (
            psycopg.OperationalError("offline"),
            psycopg.errors.InsufficientPrivilege("denied"),
        ):
            with self.subTest(error=type(error).__name__):
                with patch(
                    "scripts.bootstrap_database.psycopg.connect", side_effect=error
                ) as connect:
                    with self.assertRaises(type(error)):
                        ensure_database(URL)
                    self.assertLessEqual(connect.call_count, 2)

    def test_missing_database_uses_autocommit_and_identifier_quoting(self):
        maintenance = MagicMock()
        connection = maintenance.__enter__.return_value
        connection.closed = connection.broken = False
        connection.info.user = "operator"
        connection.execute.return_value.fetchone.return_value = None
        with patch(
            "scripts.bootstrap_database.psycopg.connect",
            side_effect=[psycopg.errors.InvalidCatalogName("missing"), maintenance, MagicMock()],
        ) as connect:
            self.assertTrue(ensure_database(URL))
        self.assertTrue(connect.call_args_list[1].kwargs["autocommit"])
        queries = [call.args[0] for call in connection.execute.call_args_list]
        create = next(query for query in queries if not isinstance(query, str))
        self.assertEqual(create.as_string(), 'CREATE DATABASE "test_db" OWNER "operator"')
        self.assertEqual(queries[-1], "SELECT pg_advisory_unlock(%s)")

    def test_bootstrap_cannot_create_the_target_on_another_server(self):
        with patch(
            "scripts.bootstrap_database.psycopg.connect",
            side_effect=psycopg.errors.InvalidCatalogName("missing"),
        ):
            with self.assertRaisesRegex(ValueError, "SERVER_MISMATCH"):
                ensure_database(URL, "postgresql://operator:secret@another-host/postgres")
