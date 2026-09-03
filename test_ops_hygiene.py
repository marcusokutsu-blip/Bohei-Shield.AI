#!/usr/bin/env python3
"""Product hygiene: ops log, required clerk, atomic persist, rotate + rewrap."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from wrapper import (
        CRYPTO_AVAILABLE,
        OPS_LOG_NAME,
        PersistClosed,
        BoheiShield,
        Envelope,
        HealthSnapshot,
        atomic_write,
    )
except ImportError:
    from bohei_shield import (
        CRYPTO_AVAILABLE,
        OPS_LOG_NAME,
        PersistClosed,
        BoheiShield,
        Envelope,
        HealthSnapshot,
        atomic_write,
    )


def accept(_body: str):
    return True, "accepted"


class HygieneTests(unittest.TestCase):
    def test_atomic_write_replaces(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "blob.bin"
            atomic_write(p, b"one")
            atomic_write(p, b"two")
            self.assertEqual(p.read_bytes(), b"two")
            self.assertFalse((Path(td) / "blob.bin.tmp").exists())

    def test_live_bind_requires_clerk(self):
        with tempfile.TemporaryDirectory() as td:
            bs = BoheiShield(persist_dir=Path(td), require_clerk=True)
            bs.register("scribe", lane=2, caps={"emit_marked": True})
            r = bs.handle(
                Envelope(type="query", actor="scribe", body="[AXIOM] law", marked=True),
                HealthSnapshot(),
            )
            self.assertEqual(r["decision"], "DENY")
            self.assertIn("claim_clerk required", r["message"])

    def test_clerk_exception_fail_closed(self):
        def boom(_body: str):
            raise RuntimeError("down")

        with tempfile.TemporaryDirectory() as td:
            bs = BoheiShield(persist_dir=Path(td), claim_clerk=boom)
            bs.register("scribe", lane=2, caps={"emit_marked": True})
            r = bs.handle(
                Envelope(type="query", actor="scribe", body="[LEAN] x", marked=True),
                HealthSnapshot(),
            )
            self.assertEqual(r["decision"], "DENY")
            self.assertIn("clerk exception", r["message"])

    def test_ops_log_written(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bs = BoheiShield(persist_dir=root, claim_clerk=accept, require_clerk=True)
            bs.register("scribe", lane=2, caps={"read_vaults": True}, talk_to=["oracle"])
            bs.handle(Envelope(type="query", actor="scribe", body="status"), HealthSnapshot())
            log = (root / OPS_LOG_NAME).read_text()
            self.assertIn('"event":"decision"', log)
            for banned in ("master_secret", "INSECURE", "psi", "vault_tile"):
                self.assertNotIn(banned, log)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography not installed")
    def test_rotate_rewrap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bs = BoheiShield(persist_dir=root, claim_clerk=accept)
            bs.register("scribe", lane=2, caps={"persist_spillway": True}, talk_to=["oracle"])
            bs.handle(Envelope(type="persist", actor="scribe", body="keep"), HealthSnapshot())
            path = root / "episodic.bsai"
            before = path.read_bytes()
            gen0 = bs.seal.generation
            out = bs.rotate_and_rewrap()
            after = path.read_bytes()
            self.assertNotEqual(before, after)
            self.assertEqual(out["generation"], gen0 + 1)
            plain = bs.seal.unwrap(after)
            self.assertTrue(plain.startswith(b"[") or plain.startswith(b'"'))
            with self.assertRaises(Exception):
                from wrapper import EnvelopeSeal

                EnvelopeSeal(b"\x00" * 32).unwrap(after)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography not installed")
    def test_rotate_refused_when_frozen(self):
        with tempfile.TemporaryDirectory() as td:
            bs = BoheiShield(persist_dir=Path(td), claim_clerk=accept)
            bs.seals_frozen = True
            with self.assertRaises(PersistClosed):
                bs.rotate_and_rewrap()


if __name__ == "__main__":
    unittest.main(verbosity=2)
