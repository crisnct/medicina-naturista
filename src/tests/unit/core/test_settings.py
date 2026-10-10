"""Runtime configuration isolation, positivity and budget relationships."""

import os
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest.mock import patch

from backend.config import Settings


class SettingsTests(unittest.TestCase):
    def test_two_environment_maps_are_independent_and_defaults_do_not_read_env(self):
        first = Settings.from_env(
            {"MAX_ACTIVE_SESSIONS": "7", "OWNER_KEY": "first", "COOKIE_SECURE": "true"}
        )
        second = Settings.from_env({"MAX_ACTIVE_SESSIONS": "8", "OWNER_KEY": "second"})
        self.assertEqual(first.max_active_sessions, 7)
        self.assertEqual(second.max_active_sessions, 8)
        self.assertTrue(first.cookie_secure)
        self.assertFalse(second.cookie_secure)
        self.assertNotIn("first", repr(first))
        with patch.dict(os.environ, {"MAX_ACTIVE_SESSIONS": "999"}):
            self.assertEqual(Settings().max_active_sessions, 100)
        self.assertEqual(Settings.from_env({}).max_active_sessions, 100)
        self.assertEqual(Settings.from_env({}).operation_timeout_seconds, 600)
        public = Settings.from_env({"PUBLIC_ORIGIN": "https://public.example/"})
        self.assertEqual(public.public_origin, "https://public.example")

    def test_invalid_or_incoherent_limits_are_rejected(self):
        for env in (
            {"MAX_ACTIVE_SESSIONS": "0"},
            {"MAX_PDF_BYTES": "0"},
            {"COOKIE_SECURE": "maybe"},
            {"SESSION_IDLE_SECONDS": "15000"},
            {"MAX_SESSION_BYTES": "10"},
            {"MAX_GLOBAL_BYTES": "100"},
            {"PUBLIC_ROOT_PATH": "//evil.invalid"},
            {"PUBLIC_ROOT_PATH": "/a?secret"},
            {"PUBLIC_ROOT_PATH": "/../other"},
            {"PUBLIC_ORIGIN": "https://public.example/medicina"},
            {"PUBLIC_ORIGIN": "https://user:secret@public.example"},
            {"PUBLIC_ORIGIN": "https://public.example?key=secret"},
            {"PUBLIC_ORIGIN": "https://public.example#fragment"},
            {"PUBLIC_ORIGIN": "https://public.example:invalid"},
            {"PUBLIC_ORIGIN": "https://public.example:65536"},
            {"PUBLIC_ORIGIN": "https://public.example:0"},
            {"PUBLIC_ORIGIN": "https://public.example\n.evil.example"},
            {"PUBLIC_ORIGIN": "*"},
        ):
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env(env)
        with self.assertRaises(ValueError):
            replace(Settings(), max_requests_per_minute=-1)

    def test_importing_application_and_factory_performs_no_infrastructure_io(self):
        code = """
from unittest.mock import patch
with patch('psycopg.connect', side_effect=AssertionError('connect at import')), patch('psycopg_pool.ConnectionPool', side_effect=AssertionError('pool at import')), patch('pathlib.Path.mkdir', side_effect=AssertionError('mkdir at import')), patch('shutil.rmtree', side_effect=AssertionError('cleanup at import')):
    from backend.web.main import create_app
    create_app()
"""
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)
