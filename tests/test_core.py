"""Тесты шины handoff: идемпотентность, эксклюзивность, восстановление, совместимость с CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ack, listing, nack, post, stats, sweep, take, wait  # noqa: E402


class HandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="handoff-test-")
        os.environ["HANDOFF_HOME"] = self.tmp

    def tearDown(self) -> None:
        os.environ.pop("HANDOFF_HOME", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_post_is_idempotent_by_key(self) -> None:
        first = post("inbox", "detmold", "hold, do not send", to="careeressa")
        second = post("inbox", "detmold", "hold, do not send", to="careeressa")
        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertFalse(first["data"]["duplicate"])
        self.assertTrue(second["data"]["duplicate"])
        self.assertEqual(stats()["data"]["totals"]["queue"], 1)

    def test_take_is_exclusive(self) -> None:
        post("inbox", "k1", "one message", to="careeressa")
        first = take("inbox", "careeressa", lease=60)
        second = take("inbox", "careeressa", lease=60)
        self.assertIsNotNone(first["data"])
        self.assertIsNone(second["data"])
        self.assertEqual(second["note"], "nothing to take for careeressa in inbox")

    def test_ack_moves_to_done(self) -> None:
        post("inbox", "k1", "x")
        take("inbox", "worker")
        self.assertTrue(ack("inbox", "k1")["success"])
        self.assertEqual(stats()["data"]["totals"]["done"], 1)
        self.assertEqual(stats()["data"]["totals"]["leased"], 0)

    def test_ack_without_lease_fails(self) -> None:
        post("inbox", "k1", "x")
        result = ack("inbox", "k1")
        self.assertFalse(result["success"])
        self.assertIn("not leased", result["error"])

    def test_recipient_filter(self) -> None:
        post("inbox", "for-a", "a", to="alpha")
        post("inbox", "for-b", "b", to="beta")
        got = take("inbox", "beta")
        self.assertEqual(got["data"]["key"], "for-b")

    def test_delay_hides_message(self) -> None:
        post("inbox", "later", "in a minute", delay=60)
        self.assertIsNone(take("inbox", "worker")["data"])
        self.assertEqual(listing("inbox")["data"]["count"], 1)

    def test_sweep_returns_expired_lease(self) -> None:
        post("inbox", "crash", "survives a dead consumer")
        take("inbox", "worker", lease=1)
        time.sleep(1.2)
        returned = sweep("inbox")
        self.assertEqual(returned["data"]["count"], 1)
        again = take("inbox", "worker", lease=60)
        self.assertEqual(again["data"]["attempts"], 2)

    def test_nack_goes_dead_after_limit(self) -> None:
        post("inbox", "poison", "always fails")
        take("inbox", "worker")
        nack("inbox", "poison", max_attempts=1)
        self.assertEqual(stats()["data"]["totals"]["dead"], 1)

    def test_wait_returns_when_message_arrives(self) -> None:
        post("inbox", "now", "already here")
        result = wait("inbox", "worker", lease=30, timeout=1)
        self.assertIsNotNone(result["data"])
        self.assertEqual(result["data"]["key"], "now")

    def test_wait_times_out(self) -> None:
        result = wait("inbox", "worker", timeout=0)
        self.assertIsNone(result["data"])
        self.assertIn("nothing to take", result["note"])

    def test_invalid_key_rejected(self) -> None:
        result = post("inbox", "../../etc/passwd", "escape attempt")
        self.assertFalse(result["success"])
        self.assertIn("invalid key", result["error"])

    def test_interoperates_with_rust_binary(self) -> None:
        """Плагин и CLI-бинарь должны видеть одну очередь — иначе это две шины."""
        binary = shutil.which("handoff") or "/home/lain/.local/bin/handoff"
        if not Path(binary).exists():
            self.skipTest("handoff binary is not installed")

        post("shared", "from-plugin", "posted by the plugin", to="*")
        env = dict(os.environ, HANDOFF_HOME=self.tmp)
        listing_out = subprocess.run(
            [binary, "list", "--channel", "shared"], capture_output=True, text=True, env=env, check=False
        )
        self.assertIn("from-plugin", listing_out.stdout)

        subprocess.run(
            [binary, "post", "--channel", "shared", "--key", "from-binary", "--", "posted by the CLI"],
            capture_output=True, text=True, env=env, check=False,
        )
        keys = [m["key"] for m in listing("shared")["data"]["messages"]]
        self.assertIn("from-binary", keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
