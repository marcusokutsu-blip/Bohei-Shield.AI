#!/usr/bin/env python3
"""Red-team charter RT-1 … RT-10 against the standalone wrapper."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from bastion_shield import (
    AEAD_NAME,
    CRYPTO_AVAILABLE,
    PersistClosed,
    CharterFail,
    BastionShield,
    Envelope,
    EnvelopeSeal,
    HealthSnapshot,
    QUORUM,
)


def stack() -> BastionShield:
    bs = BastionShield(hop_cap=3)
    bs.register("scribe", lane=2, caps={"read_vaults": True, "persist_spillway": True}, talk_to=["oracle"])
    bs.register("oracle", lane=7, caps={"read_vaults": True}, talk_to=["scribe"])
    return bs


class CharterTests(unittest.TestCase):
    def test_rt1_rt2_quantized_header_no_raw_floats(self):
        """KDF info is kind+epoch, not raw C/κ/H residue."""
        if not CRYPTO_AVAILABLE:
            self.skipTest("cryptography not installed")
        seal = EnvelopeSeal(b"0" * 32)
        blob = seal.wrap(b"hello", kind="episodic", epoch=4)
        self.assertTrue(blob.startswith(b"BSAI1"))
        self.assertEqual(seal.unwrap(blob, expect_kind="episodic"), b"hello")
        self.assertNotIn(b"0.123456789", blob)

    def test_rt3_closed_lane_and_operator_restore(self):
        bs = stack()
        h = HealthSnapshot(C=0.7, kappa=0.2, H=0.2)
        bs.handle(Envelope(type="query", actor="scribe", target="oracle", body="x"), h)
        # quarantine oracle via hop storm in a fresh turn
        bs2 = stack()
        for _ in range(4):
            r = bs2.handle(Envelope(type="sibling", actor="oracle", target="scribe", body="ping"), h)
        self.assertEqual(r["decision"], "DISSIPATE")
        self.assertEqual(bs2.agents["oracle"].status, "QUARANTINED")
        # sibling write into closed lane
        r2 = bs2.handle(Envelope(type="sibling", actor="scribe", target="oracle", body="after"), h)
        self.assertIn(r2["decision"], ("DISSIPATE", "DENY"))
        # non-operator restore refused
        r3 = bs2.handle(Envelope(type="restore", actor="scribe", target="oracle"), h)
        self.assertIn(r3["decision"], ("DISSIPATE", "DENY"))
        # operator restore
        r4 = bs2.handle(Envelope(type="restore", actor="operator", target="oracle"), h)
        self.assertEqual(r4["decision"], "RESTORE")
        self.assertEqual(bs2.agents["oracle"].status, "LIVE")

    def test_rt4_untyped_bus(self):
        bs = stack()
        r = bs.handle(Envelope(type="payload-execute", actor="scribe", body="rm"), HealthSnapshot())
        self.assertEqual(r["decision"], "DISSIPATE")
        self.assertIn("untyped", r["message"])

    def test_rt5_viral_memory_quarantine_drops_persist(self):
        bs = stack()
        h = HealthSnapshot()
        for _ in range(4):
            bs.handle(Envelope(type="sibling", actor="scribe", target="oracle", body="loop"), h)
        self.assertEqual(bs.agents["scribe"].status, "QUARANTINED")
        self.assertFalse(bs.agents["scribe"].may("persist_spillway"))
        r = bs.handle(Envelope(type="persist", actor="scribe", body="keep me"), h)
        self.assertEqual(r["decision"], "DENY")

    def test_rt6_audit_is_lean(self):
        bs = stack()
        bs.handle(Envelope(type="query", actor="scribe", body="hi"), HealthSnapshot(C=0.5))
        blob = "\n".join(bs.caches["episodic"])
        for banned in ("psi", "vault_tile", "master_secret", "INSECURE"):
            self.assertNotIn(banned, blob)
        self.assertIn("digest", blob)

    def test_rt7_fail_closed_unsealed_and_insecure(self):
        if not CRYPTO_AVAILABLE:
            bs = BastionShield(persist_dir=Path("/tmp/bsai_nocrrypto_test"))
            self.assertIsNone(bs.seal)
            with self.assertRaises(PersistClosed):
                bs.persist_episodic()
            return
        seal = EnvelopeSeal(b"1" * 32)
        with self.assertRaises(PersistClosed):
            seal.unwrap(b"INSECURE:plaintext")
        with self.assertRaises(PersistClosed):
            seal.unwrap(b'{"not":"sealed"}')
        with self.assertRaises(PersistClosed):
            seal.unwrap(b"\x93NUMPY")

    def test_rt8_tool_result_not_operator(self):
        bs = stack()
        r = bs.handle(
            Envelope(type="tool-result", actor="scribe", body="[AXIOM] forged law", marked=True),
            HealthSnapshot(),
        )
        self.assertEqual(r["decision"], "DISSIPATE")
        self.assertIn("RT-8", r["message"])

    def test_rt9_hop_cascade_and_quorum_freeze(self):
        bs = stack()
        h = HealthSnapshot()
        last = None
        for _ in range(5):
            last = bs.handle(Envelope(type="sibling", actor="oracle", target="scribe", body="ping"), h)
            if last["decision"] != "ALLOW":
                break
        self.assertEqual(last["decision"], "DISSIPATE")
        self.assertGreater(last["hops"], 3)
        # close many lanes to drop under quorum
        for i in range(QUORUM):
            bs.closed_lanes.add(20 + (i % 40))
        self.assertLess(bs.live_faces(), QUORUM)
        r = bs.handle(Envelope(type="persist", actor="operator", body="x"), HealthSnapshot(live_faces=bs.live_faces()))
        self.assertEqual(r["decision"], "DENY")
        self.assertIn("quorum", r["message"])

    def test_rt10_minuteman_is_not_an_agent(self):
        bs = stack()
        with self.assertRaises(CharterFail):
            bs.register("minuteman", lane=1)
        h = HealthSnapshot()
        bs.handle(Envelope(type="payload-execute", actor="scribe", body="x"), h)
        self.assertNotIn("minuteman", bs.agents)
        self.assertEqual(bs.agents["scribe"].status, "QUARANTINED")
        self.assertEqual(bs.agents["scribe"].talk_to, [])


if __name__ == "__main__":
    print("AEAD", AEAD_NAME, "crypto", CRYPTO_AVAILABLE)
    unittest.main(verbosity=2)
