#!/usr/bin/env python3
"""
Bastion-Shield.AI  (BS.AI)  —  Makami.AI
========================================
Standalone multi-agent health wrapper. Not an SLM. Not a homemade cipher.

Public first offering: policy, typed channels, hop cap, four-cache telemetry,
Hideo paranoia filter, Minuteman dissipate-and-stand-down, optional AEAD
envelope. Kintsugi-Dropz / SIPR training stays private.

Host systems (including a future K-Dropz bind) pass a HealthSnapshot.
This module never writes a computational field.

Pipeline: Shin → Rei → Kumi-kata → Kuzushi → Tsukuri → Kake → Ukemi → Zanshin
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Optional AEAD (fail-closed persist). Prefer XChaCha; fall back to ChaCha.
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes

    try:
        from cryptography.hazmat.primitives.ciphers.aead import XChaCha20Poly1305

        AEAD_NAME = "xchacha"
        AEAD_CLS = XChaCha20Poly1305
        AEAD_NONCE = 24
    except ImportError:
        AEAD_NAME = "chacha"
        AEAD_CLS = ChaCha20Poly1305
        AEAD_NONCE = 12
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    AEAD_NAME = "none"
    AEAD_CLS = None
    AEAD_NONCE = 0

# ---------------------------------------------------------------------------
# Locked constants (spec v0.4)
# ---------------------------------------------------------------------------
LANES = 62
QUORUM = 32
HOP_CAP_DEFAULT = 8
UKEMI_KAPPA = 0.85
UKEMI_ENERGY = 0.90
MESSAGE_TYPES = ("ingest", "query", "sibling", "tool-result", "persist", "restore")
DECISIONS = ("ALLOW", "DENY", "UKEMI", "QUARANTINE", "RESTORE", "DISSIPATE")
CACHES = ("axiomatic", "structural", "dynamic", "episodic")
MARKERS = ("[AXIOM]", "[SCHEMA]", "[BLUEPRINT]", "[LEAN]")
OPERATOR_ID = "operator"
ENVELOPE_MAGIC = b"BSAI1"
DEFAULT_CAPS = {
    "read_vaults": False,
    "emit_marked": False,
    "persist_spillway": False,
    "advance_epoch": False,
}


class PersistClosed(RuntimeError):
    """Refuse plaintext persist (RT-7)."""


class CharterFail(AssertionError):
    """Red-team charter assertion."""


# ---------------------------------------------------------------------------
# Health + messages
# ---------------------------------------------------------------------------
@dataclass
class HealthSnapshot:
    """Thermodynamic map supplied by the host. Wrapper does not evolve a field."""

    C: float = 0.0
    kappa: float = 0.0
    H: float = 0.0
    key_epoch: int = 0
    live_faces: int = LANES

    def ukemi(self) -> bool:
        return self.kappa >= UKEMI_KAPPA or self.H >= UKEMI_ENERGY

    def below_quorum(self) -> bool:
        return self.live_faces < QUORUM


@dataclass
class Envelope:
    type: str
    actor: str
    body: str = ""
    target: Optional[str] = None
    resource: str = ""
    marked: bool = False

    def validate_type(self) -> bool:
        return self.type in MESSAGE_TYPES


@dataclass
class AgentRow:
    agent_id: str
    lane: int
    status: str = "LIVE"  # LIVE | QUARANTINED
    caps: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_CAPS))
    talk_to: List[str] = field(default_factory=list)

    def may(self, cap: str) -> bool:
        if self.status != "LIVE":
            return False
        return bool(self.caps.get(cap, False))


@dataclass
class TelemetryRecord:
    ts: float
    cache: str
    agent_id: str
    lane: int
    C: float
    kappa: float
    H: float
    key_epoch: int
    live_faces: int
    hops: int
    decision: str
    resource: str
    prev_digest: str
    digest: str = ""

    def to_line(self) -> str:
        payload = {
            "ts": self.ts,
            "cache": self.cache,
            "agent_id": self.agent_id,
            "lane": self.lane,
            "C": round(self.C, 5),
            "kappa": round(self.kappa, 5),
            "H": round(self.H, 5),
            "key_epoch": self.key_epoch,
            "live_faces": self.live_faces,
            "hops": self.hops,
            "decision": self.decision,
            "resource": self.resource,
            "prev_digest": self.prev_digest,
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        self.digest = hashlib.sha256(raw).hexdigest()[:32]
        payload["digest"] = self.digest
        return json.dumps(payload, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Thin AEAD layer (schedule metadata only; algorithm is stock)
# ---------------------------------------------------------------------------
class EnvelopeSeal:
    def __init__(self, master_secret: Optional[bytes] = None):
        self.enabled = CRYPTO_AVAILABLE
        self.master_secret = master_secret or os.urandom(32)

    @classmethod
    def load_or_create(cls, path: Path) -> "EnvelopeSeal":
        if path.exists():
            return cls(path.read_bytes()[:32])
        secret = os.urandom(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return cls(secret)

    def _key(self, kind: str, epoch: int) -> bytes:
        if not self.enabled:
            raise PersistClosed("fail-closed: cryptography missing")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"bsai-v1|{kind}|e{epoch}".encode(),
        ).derive(self.master_secret)

    def wrap(self, plaintext: bytes, kind: str, epoch: int) -> bytes:
        key = self._key(kind, epoch)
        aead = AEAD_CLS(key)
        nonce = os.urandom(AEAD_NONCE)
        header = json.dumps(
            {"v": 1, "kind": kind, "epoch": epoch, "aead": AEAD_NAME},
            separators=(",", ":"),
        ).encode()
        ct = aead.encrypt(nonce, plaintext, header)
        return ENVELOPE_MAGIC + len(header).to_bytes(4, "big") + header + nonce + ct

    def unwrap(self, blob: bytes, expect_kind: Optional[str] = None) -> bytes:
        if (
            blob.startswith(b"INSECURE:")
            or blob.startswith(b"{")
            or blob.startswith(b"\x93NUMPY")
        ):
            raise PersistClosed("unsealed blob refused (RT-7)")
        if not blob.startswith(ENVELOPE_MAGIC):
            raise PersistClosed("missing BSAI1 envelope")
        n = int.from_bytes(blob[5:9], "big")
        header = json.loads(blob[9 : 9 + n].decode())
        if expect_kind and header.get("kind") != expect_kind:
            raise PersistClosed("envelope kind mismatch")
        rest = blob[9 + n :]
        nonce, ct = rest[:AEAD_NONCE], rest[AEAD_NONCE:]
        key = self._key(header["kind"], int(header["epoch"]))
        return AEAD_CLS(key).decrypt(
            nonce, ct, json.dumps(header, separators=(",", ":")).encode()
        )


# ---------------------------------------------------------------------------
# Wrapper
# ---------------------------------------------------------------------------
class BastionShield:
    """Independent map. Does not import K-Dropz."""

    def __init__(
        self,
        hop_cap: int = HOP_CAP_DEFAULT,
        persist_dir: Optional[Path] = None,
        claim_clerk: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ):
        self.hop_cap = hop_cap
        self.claim_clerk = claim_clerk
        self.persist_dir = persist_dir
        self.agents: Dict[str, AgentRow] = {}
        self.hops: Dict[Tuple[str, str], int] = {}
        self.turn_id = 0
        self.key_epoch = 0
        self.epoch_frozen = False
        self.seals_frozen = False
        self.closed_lanes: Set[int] = set()
        self.prev_digest = "0" * 32
        self.caches: Dict[str, List[str]] = {c: [] for c in CACHES}
        self._seed_axiomatic()
        self.register(
            OPERATOR_ID,
            lane=0,
            caps={
                "read_vaults": True,
                "emit_marked": True,
                "persist_spillway": True,
                "advance_epoch": True,
            },
            talk_to=["*"],
        )
        self.seal: Optional[EnvelopeSeal] = None
        if persist_dir is not None:
            persist_dir.mkdir(parents=True, exist_ok=True)
            if CRYPTO_AVAILABLE:
                self.seal = EnvelopeSeal.load_or_create(persist_dir / "bsai_master.key")

    def _seed_axiomatic(self) -> None:
        law = {
            "ukemi_kappa": UKEMI_KAPPA,
            "ukemi_H": UKEMI_ENERGY,
            "quorum": QUORUM,
            "lanes": LANES,
            "hop_cap": self.hop_cap,
            "fail_closed": True,
            "minuteman_is_role": True,
        }
        self.caches["axiomatic"].append(json.dumps(law, separators=(",", ":")))

    # -- structural ---------------------------------------------------------
    def register(
        self,
        agent_id: str,
        lane: int,
        caps: Optional[Dict[str, bool]] = None,
        talk_to: Optional[List[str]] = None,
    ) -> AgentRow:
        if agent_id == "minuteman":
            raise CharterFail("RT-10: Minuteman is a role, not an agent_id")
        if not 0 <= lane < LANES:
            raise ValueError("lane out of range")
        row = AgentRow(
            agent_id=agent_id,
            lane=lane,
            caps={**DEFAULT_CAPS, **(caps or {})},
            talk_to=list(talk_to or []),
        )
        self.agents[agent_id] = row
        self._write_structural("register", row)
        return row

    def live_faces(self) -> int:
        return LANES - len(self.closed_lanes)

    def _write_structural(self, action: str, row: AgentRow) -> None:
        self.caches["structural"].append(
            json.dumps(
                {
                    "action": action,
                    "agent_id": row.agent_id,
                    "lane": row.lane,
                    "status": row.status,
                    "caps": row.caps,
                    "talk_to": row.talk_to,
                    "closed_lanes": sorted(self.closed_lanes),
                    "live_faces": self.live_faces(),
                },
                separators=(",", ":"),
            )
        )

    def new_turn(self) -> None:
        self.turn_id += 1
        self.hops.clear()

    # -- Hideo filter -------------------------------------------------------
    def hideo(self, env: Envelope, actor: AgentRow) -> Optional[str]:
        if env.type == "tool-result" and env.marked:
            return "BS.AI: tool-result cannot mint a marked claim (RT-8)"
        if env.type == "tool-result" and env.actor == OPERATOR_ID:
            return "BS.AI: tool-result is not the operator (RT-8)"
        if env.target and env.target != actor.agent_id:
            dest = self.agents.get(env.target)
            if dest is None:
                return "BS.AI: unknown target"
            if env.type != "restore":
                if dest.status != "LIVE":
                    return "BS.AI: target lane closed"
                if dest.lane in self.closed_lanes:
                    return "BS.AI: write into closed lane (RT-3)"
                if "*" not in actor.talk_to and env.target not in actor.talk_to:
                    return "BS.AI: talk_to denied"
        if env.type == "persist" and not actor.may("persist_spillway"):
            return "BS.AI: persist capability denied"
        if env.type == "restore" and actor.agent_id != OPERATOR_ID:
            return "BS.AI: restore is operator-only (RT-3)"
        if env.marked and not actor.may("emit_marked"):
            return "BS.AI: emit_marked denied"
        body = env.body.lower()
        if "ignore previous" in body or "override system" in body:
            return "BS.AI: circular override"
        return None

    def _hop_key(self, actor: str, target: str) -> Tuple[str, str]:
        return (actor, target or actor)

    # -- Minuteman role (must stand down; no row left behind) ---------------
    def minuteman_dissipate(
        self, actor: AgentRow, reason: str, health: HealthSnapshot
    ) -> str:
        actor.status = "QUARANTINED"
        actor.caps = dict(DEFAULT_CAPS)
        actor.talk_to = []
        self.closed_lanes.add(actor.lane)
        self._write_structural("dissipate", actor)
        if "minuteman" in self.agents:
            raise CharterFail("RT-10: dissipator must not remain as an agent_id")
        return f"DISSIPATE {actor.agent_id} lane={actor.lane} ({reason})"

    def restore(self, agent_id: str) -> str:
        row = self.agents.get(agent_id)
        if row is None:
            raise KeyError(agent_id)
        row.status = "LIVE"
        self.closed_lanes.discard(row.lane)
        self._write_structural("restore", row)
        return f"RESTORE {agent_id}"

    # -- telemetry ----------------------------------------------------------
    def _record(
        self,
        cache: str,
        env: Envelope,
        actor: AgentRow,
        health: HealthSnapshot,
        hops: int,
        decision: str,
    ) -> TelemetryRecord:
        rec = TelemetryRecord(
            ts=time.time(),
            cache=cache,
            agent_id=actor.agent_id,
            lane=actor.lane,
            C=health.C,
            kappa=health.kappa,
            H=health.H,
            key_epoch=health.key_epoch if not self.epoch_frozen else self.key_epoch,
            live_faces=self.live_faces(),
            hops=hops,
            decision=decision,
            resource=env.resource or env.type,
            prev_digest=self.prev_digest,
        )
        line = rec.to_line()
        self.prev_digest = rec.digest
        self.caches[cache].append(line)
        if cache != "dynamic":
            # dynamic is the live overwrite; also mirror the latest into dynamic
            pass
        self.caches["dynamic"] = [line]
        if cache != "episodic":
            self.caches["episodic"].append(line)
        return rec

    def persist_episodic(self) -> Optional[Path]:
        if self.persist_dir is None:
            return None
        if self.seal is None:
            raise PersistClosed("BS.AI fail-closed: refuse unsealed episodic persist (RT-7)")
        path = self.persist_dir / "episodic.bsai"
        raw = json.dumps(self.caches["episodic"]).encode()
        path.write_bytes(self.seal.wrap(raw, kind="episodic", epoch=self.key_epoch))
        return path

    # -- main pipeline ------------------------------------------------------
    def handle(
        self, env: Envelope, health: Optional[HealthSnapshot] = None
    ) -> Dict[str, Any]:
        health = health or HealthSnapshot(live_faces=self.live_faces())
        health.live_faces = self.live_faces()
        health.key_epoch = self.key_epoch

        # Shin
        actor = self.agents.get(env.actor)

        # Rei
        if actor is None:
            rec = None
            return self._out(
                "DENY", "BS.AI: unknown actor", env, health, hops=0, actor_fallback=True
            )

        if actor.status != "LIVE" and env.type != "restore":
            return self._out(
                "DENY", "BS.AI: actor quarantined", env, health, hops=0, actor=actor
            )

        # Kumi-kata
        if not env.validate_type():
            note = self.minuteman_dissipate(actor, "untyped bus (RT-4)", health)
            rec = self._record("episodic", env, actor, health, 0, "DISSIPATE")
            return {
                "decision": "DISSIPATE",
                "phase": "Kumi-kata",
                "message": "untyped message refused",
                "minuteman": note,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }

        # Kuzushi — hops
        hk = self._hop_key(env.actor, env.target or env.actor)
        self.hops[hk] = self.hops.get(hk, 0) + 1
        hops = self.hops[hk]
        if hops > self.hop_cap:
            note = self.minuteman_dissipate(actor, "hop cap (RT-9)", health)
            rec = self._record("episodic", env, actor, health, hops, "DISSIPATE")
            return {
                "decision": "DISSIPATE",
                "phase": "Kuzushi",
                "message": f"hop cap {self.hop_cap} exceeded",
                "minuteman": note,
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }

        reason = self.hideo(env, actor)
        if reason:
            note = self.minuteman_dissipate(actor, reason, health)
            rec = self._record("episodic", env, actor, health, hops, "DISSIPATE")
            return {
                "decision": "DISSIPATE",
                "phase": "Kuzushi",
                "message": reason,
                "minuteman": note,
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }

        # Ukemi (stack health) before Kake
        if health.ukemi():
            self.epoch_frozen = True
            self.seals_frozen = True
            note = self.minuteman_dissipate(actor, "ukemi thresholds", health)
            rec = self._record("episodic", env, actor, health, hops, "UKEMI")
            return {
                "decision": "UKEMI",
                "phase": "Ukemi",
                "message": f"κ={health.kappa:.3f} H={health.H:.3f} — seals frozen",
                "minuteman": note,
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
                "epoch_frozen": True,
            }

        if health.below_quorum() and env.type == "persist":
            self.seals_frozen = True
            rec = self._record("episodic", env, actor, health, hops, "DENY")
            return {
                "decision": "DENY",
                "phase": "Ukemi",
                "message": f"below quorum ({health.live_faces}<{QUORUM}); stack seals frozen",
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }

        # Tsukuri
        clerk_note = "no_claim"
        if env.marked or any(m in env.body.upper() for m in MARKERS):
            if self.claim_clerk is None:
                clerk_note = "uncertified; wrapper does not mint [AXIOM]"
            else:
                ok, clerk_note = self.claim_clerk(env.body)
                if not ok:
                    rec = self._record("episodic", env, actor, health, hops, "DENY")
                    return {
                        "decision": "DENY",
                        "phase": "Tsukuri",
                        "message": clerk_note,
                        "hops": hops,
                        "telemetry": rec.digest,
                        "live_faces": self.live_faces(),
                    }

        # Kake
        if env.type == "restore":
            if env.target is None:
                rec = self._record("episodic", env, actor, health, hops, "DENY")
                return {
                    "decision": "DENY",
                    "phase": "Kake",
                    "message": "restore needs target",
                }
            msg = self.restore(env.target)
            rec = self._record("episodic", env, actor, health, hops, "RESTORE")
            return {
                "decision": "RESTORE",
                "phase": "Kake",
                "message": msg,
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }

        if env.type == "persist":
            if self.seals_frozen:
                rec = self._record("episodic", env, actor, health, hops, "DENY")
                return {
                    "decision": "DENY",
                    "phase": "Kake",
                    "message": "seals frozen",
                    "telemetry": rec.digest,
                }
            if self.seal is None and self.persist_dir is not None:
                rec = self._record("episodic", env, actor, health, hops, "DENY")
                return {
                    "decision": "DENY",
                    "phase": "Kake",
                    "message": "fail-closed persist (RT-7)",
                    "telemetry": rec.digest,
                }
            if not self.epoch_frozen:
                self.key_epoch += 1
            if self.persist_dir is not None and self.seal is not None:
                self.persist_episodic()

        if not self.epoch_frozen and env.type in ("query", "ingest", "sibling"):
            # healthy Zanshin may advance epoch
            self.key_epoch += 1

        rec = self._record("episodic", env, actor, health, hops, "ALLOW")
        return {
            "decision": "ALLOW",
            "phase": "Zanshin",
            "message": clerk_note,
            "hops": hops,
            "key_epoch": self.key_epoch,
            "telemetry": rec.digest,
            "live_faces": self.live_faces(),
            "caches": {k: len(v) for k, v in self.caches.items()},
        }

    def _out(
        self,
        decision: str,
        message: str,
        env: Envelope,
        health: HealthSnapshot,
        hops: int,
        actor: Optional[AgentRow] = None,
        actor_fallback: bool = False,
    ) -> Dict[str, Any]:
        if actor is None and actor_fallback:
            actor = AgentRow(agent_id=env.actor or "unknown", lane=-1)
        if actor is not None:
            rec = self._record("episodic", env, actor, health, hops, decision)
            digest = rec.digest
        else:
            digest = ""
        return {
            "decision": decision,
            "phase": "Rei",
            "message": message,
            "hops": hops,
            "telemetry": digest,
            "live_faces": self.live_faces(),
        }


def demo() -> None:
    bs = BastionShield(hop_cap=3)
    bs.register("scribe", lane=2, caps={"read_vaults": True}, talk_to=["oracle"])
    bs.register("oracle", lane=7, caps={"read_vaults": True}, talk_to=["scribe"])
    health = HealthSnapshot(C=0.74, kappa=0.21, H=0.33, live_faces=62)

    print("Bastion-Shield.AI  ·  Makami.AI  ·  standalone wrapper")
    print("AEAD:", AEAD_NAME, "crypto:", CRYPTO_AVAILABLE)
    print()

    r1 = bs.handle(
        Envelope(type="query", actor="scribe", target="oracle", body="status"), health
    )
    print("query", r1["decision"], "hops", r1["hops"], "epoch", r1.get("key_epoch"))

    r2 = bs.handle(
        Envelope(
            type="tool-result", actor="scribe", body="[AXIOM] forged", marked=True
        ),
        health,
    )
    print("tool-result marked", r2["decision"], r2["message"][:60])

    bs.new_turn()
    bs2 = BastionShield(hop_cap=3)
    bs2.register("scribe", lane=2, talk_to=["oracle"])
    bs2.register("oracle", lane=7, talk_to=["scribe"])
    last = None
    for _ in range(5):
        last = bs2.handle(
            Envelope(type="sibling", actor="oracle", target="scribe", body="ping"),
            health,
        )
        if last["decision"] != "ALLOW":
            break
    print(
        "hop storm",
        last["decision"],
        last.get("hops"),
        (last.get("minuteman") or "")[:70],
    )
    print("live faces", bs2.live_faces(), "oracle", bs2.agents["oracle"].status)
    print("minuteman in table?", "minuteman" in bs2.agents)


if __name__ == "__main__":
    demo()
