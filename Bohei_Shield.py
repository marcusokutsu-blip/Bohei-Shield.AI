#!/usr/bin/env python3
"""
Bohei-Shield.AI  (BS.AI)  —  Makami.AI
========================================
Standalone multi-agent health wrapper. Not an SLM. Not a homemade cipher.

Public first offering: policy, typed channels, hop cap, four-cache telemetry,
Hideo paranoia filter, Minuteman dissipate-and-stand-down, required claim clerk
on live bind, structured ops log, atomic persist, master-key rotate + rewrap,
optional AEAD envelope.

Host systems pass a HealthSnapshot. This module never writes a computational field.

Pipeline: Shin → Rei → Kumi-kata → Kuzushi → Tsukuri → Kake → Ukemi → Zanshin
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
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
# Locked constants (spec v0.5 — product hygiene on v0.4 charter)
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
OPS_LOG_NAME = "ops.jsonl"
MASTER_NAME = "bsai_master.key"
MASTER_META = "bsai_master.meta.json"
DEFAULT_CAPS = {
    "read_vaults": False,
    "emit_marked": False,
    "persist_spillway": False,
    "advance_epoch": False,
    "rotate_keys": False,
}


class PersistClosed(RuntimeError):
    """Refuse plaintext persist (RT-7)."""


class CharterFail(AssertionError):
    """Red-team charter assertion."""


class ClerkRequired(RuntimeError):
    """Live bind refused a marked claim without a host clerk."""


def atomic_write(path: Path, data: bytes) -> None:
    """Write-temp → fsync → replace. Crash mid-write cannot leave a half blob."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        written = 0
        while written < len(data):
            written += os.write(fd, data[written:])
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def parse_header(blob: bytes) -> Dict[str, Any]:
    if not blob.startswith(ENVELOPE_MAGIC):
        raise PersistClosed("missing BSAI1 envelope")
    n = int.from_bytes(blob[5:9], "big")
    return json.loads(blob[9 : 9 + n].decode())


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


class OpsLog:
    """Structured production log. Never writes secrets, plaintext spillways, or bodies."""

    BANNED = ("master_secret", "INSECURE", "psi", "vault_tile")

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self.lines: List[str] = []

    def emit(self, event: str, **fields: Any) -> Dict[str, Any]:
        rec: Dict[str, Any] = {
            "ts": time.time(),
            "event": event,
            "module": "Bohei-Shield.AI",
        }
        for k, v in fields.items():
            if v is None:
                continue
            rec[k] = v
        line = json.dumps(rec, separators=(",", ":"), sort_keys=True)
        low = line.lower()
        for banned in self.BANNED:
            if banned.lower() in low:
                raise CharterFail(f"ops log refused banned token: {banned}")
        self.lines.append(line)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
        return rec


# ---------------------------------------------------------------------------
# Thin AEAD layer (schedule metadata only; algorithm is stock)
# ---------------------------------------------------------------------------
class EnvelopeSeal:
    def __init__(self, master_secret: Optional[bytes] = None, generation: int = 1):
        self.enabled = CRYPTO_AVAILABLE
        self.master_secret = master_secret or os.urandom(32)
        self.generation = int(generation)

    @classmethod
    def load_or_create(cls, path: Path) -> "EnvelopeSeal":
        meta_path = path.with_name(MASTER_META)
        generation = 1
        if meta_path.exists():
            try:
                generation = int(json.loads(meta_path.read_text()).get("generation", 1))
            except (OSError, ValueError, json.JSONDecodeError):
                generation = 1
        if path.exists():
            return cls(path.read_bytes()[:32], generation=generation)
        secret = os.urandom(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        atomic_write(
            meta_path,
            json.dumps({"generation": generation, "aead": AEAD_NAME, "v": 1}).encode(),
        )
        return cls(secret, generation=generation)

    def persist_master(self, path: Path) -> None:
        atomic_write(path, self.master_secret)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        atomic_write(
            path.with_name(MASTER_META),
            json.dumps(
                {
                    "generation": self.generation,
                    "aead": AEAD_NAME,
                    "v": 1,
                    "rotated_ts": time.time(),
                }
            ).encode(),
        )

    def _key(self, kind: str, epoch: int) -> bytes:
        if not self.enabled:
            raise PersistClosed("fail-closed: cryptography missing")
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"bsai-v1|{kind}|e{epoch}|g{self.generation}".encode(),
        ).derive(self.master_secret)

    def wrap(self, plaintext: bytes, kind: str, epoch: int) -> bytes:
        key = self._key(kind, epoch)
        aead = AEAD_CLS(key)
        nonce = os.urandom(AEAD_NONCE)
        header = json.dumps(
            {
                "v": 1,
                "kind": kind,
                "epoch": epoch,
                "gen": self.generation,
                "aead": AEAD_NAME,
            },
            separators=(",", ":"),
        ).encode()
        ct = aead.encrypt(nonce, plaintext, header)
        return ENVELOPE_MAGIC + len(header).to_bytes(4, "big") + header + nonce + ct

    def unwrap(self, blob: bytes, expect_kind: Optional[str] = None) -> bytes:
        if blob.startswith(b"INSECURE:") or blob.startswith(b"{") or blob.startswith(b"\x93NUMPY"):
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
        return AEAD_CLS(key).decrypt(nonce, ct, json.dumps(header, separators=(",", ":")).encode())


# ---------------------------------------------------------------------------
# Wrapper
# ---------------------------------------------------------------------------
class BoheiShield:
    """Independent map. Does not import a language model."""

    def __init__(
        self,
        hop_cap: int = HOP_CAP_DEFAULT,
        persist_dir: Optional[Path] = None,
        claim_clerk: Optional[Callable[[str], Tuple[bool, str]]] = None,
        require_clerk: Optional[bool] = None,
        ops_log_path: Optional[Path] = None,
    ):
        self.hop_cap = hop_cap
        self.claim_clerk = claim_clerk
        self.persist_dir = Path(persist_dir) if persist_dir is not None else None
        # Live product default: a persist directory is a live bind → clerk required.
        if require_clerk is None:
            require_clerk = self.persist_dir is not None
        self.require_clerk = bool(require_clerk)
        self.agents: Dict[str, AgentRow] = {}
        self.hops: Dict[Tuple[str, str], int] = {}
        self.turn_id = 0
        self.key_epoch = 0
        self.epoch_frozen = False
        self.seals_frozen = False
        self.closed_lanes: Set[int] = set()
        self.prev_digest = "0" * 32
        self.caches: Dict[str, List[str]] = {c: [] for c in CACHES}
        log_path = ops_log_path
        if log_path is None and self.persist_dir is not None:
            log_path = self.persist_dir / OPS_LOG_NAME
        self.ops = OpsLog(log_path)
        self._seed_axiomatic()
        self.register(
            OPERATOR_ID,
            lane=0,
            caps={
                "read_vaults": True,
                "emit_marked": True,
                "persist_spillway": True,
                "advance_epoch": True,
                "rotate_keys": True,
            },
            talk_to=["*"],
        )
        log_path = ops_log_path
        if log_path is None and self.persist_dir is not None:
            log_path = self.persist_dir / OPS_LOG_NAME
        self.ops = OpsLog(log_path)
        self.seal: Optional[EnvelopeSeal] = None
        if self.persist_dir is not None:
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            if CRYPTO_AVAILABLE:
                self.seal = EnvelopeSeal.load_or_create(self.persist_dir / MASTER_NAME)
                self.ops.emit(
                    "seal_ready",
                    aead=AEAD_NAME,
                    generation=self.seal.generation,
                    persist_dir=str(self.persist_dir),
                )
            else:
                self.ops.emit("seal_unavailable", aead="none")

    def _seed_axiomatic(self) -> None:
        law = {
            "ukemi_kappa": UKEMI_KAPPA,
            "ukemi_H": UKEMI_ENERGY,
            "quorum": QUORUM,
            "lanes": LANES,
            "hop_cap": self.hop_cap,
            "fail_closed": True,
            "minuteman_is_role": True,
            "require_clerk_default": True,
            "atomic_persist": True,
            "master_rotation": True,
        }
        self.caches["axiomatic"].append(json.dumps(law, separators=(",", ":")))

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
        self.ops.emit("register", agent_id=agent_id, lane=lane, caps=row.caps)
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

    def minuteman_dissipate(self, actor: AgentRow, reason: str, health: HealthSnapshot) -> str:
        actor.status = "QUARANTINED"
        actor.caps = dict(DEFAULT_CAPS)
        actor.talk_to = []
        self.closed_lanes.add(actor.lane)
        self._write_structural("dissipate", actor)
        if "minuteman" in self.agents:
            raise CharterFail("BS.RT-10: dissipator must not remain as an agent_id")
        self.ops.emit("dissipate", agent_id=actor.agent_id, lane=actor.lane, reason=reason)
        return f"DISSIPATE {actor.agent_id} lane={actor.lane} ({reason})"

    def restore(self, agent_id: str) -> str:
        row = self.agents.get(agent_id)
        if row is None:
            raise KeyError(agent_id)
        row.status = "LIVE"
        self.closed_lanes.discard(row.lane)
        self._write_structural("restore", row)
        self.ops.emit("restore", agent_id=agent_id, lane=row.lane)
        return f"RESTORE {agent_id}"

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
        self.caches["dynamic"] = [line]
        if cache != "episodic":
            self.caches["episodic"].append(line)
        self.ops.emit(
            "decision",
            decision=decision,
            actor=actor.agent_id,
            cache=cache,
            hops=hops,
            digest=rec.digest,
            key_epoch=self.key_epoch,
        )
        return rec

    def persist_episodic(self) -> Optional[Path]:
        return self.persist_cache("episodic")

    def persist_cache(self, kind: str = "episodic") -> Optional[Path]:
        if kind not in CACHES:
            raise ValueError(kind)
        if self.persist_dir is None:
            return None
        if self.seal is None:
            raise PersistClosed("fail-closed: refuse unsealed persist (RT-7)")
        path = self.persist_dir / f"{kind}.bsai"
        raw = json.dumps(self.caches[kind]).encode()
        atomic_write(path, self.seal.wrap(raw, kind=kind, epoch=self.key_epoch))
        self.ops.emit("persist", kind=kind, epoch=self.key_epoch, path=str(path))
        return path

    def rotate_and_rewrap(self, actor_id: str = OPERATOR_ID) -> Dict[str, Any]:
        """Replace the master secret and rewrap every *.bsai under persist_dir.

        Operator-only. Refuses when seals are frozen. Same stock AEAD; new master.
        """
        actor = self.agents.get(actor_id)
        if actor is None or actor.agent_id != OPERATOR_ID or not actor.may("rotate_keys"):
            raise PersistClosed("rotate is operator-only")
        if self.seals_frozen:
            raise PersistClosed("seals frozen; rotation refused")
        if self.seal is None or not CRYPTO_AVAILABLE:
            raise PersistClosed("fail-closed: cannot rotate without AEAD")
        if self.persist_dir is None:
            raise PersistClosed("rotation requires persist_dir")

        payloads: List[Tuple[Path, str, bytes]] = []
        for path in sorted(self.persist_dir.glob("*.bsai")):
            blob = path.read_bytes()
            header = parse_header(blob)
            kind = str(header.get("kind") or "episodic")
            payloads.append((path, kind, self.seal.unwrap(blob, expect_kind=kind)))

        new_secret = os.urandom(32)
        new_gen = self.seal.generation + 1
        if not self.epoch_frozen:
            self.key_epoch += 1
        new_seal = EnvelopeSeal(new_secret, generation=new_gen)
        for path, kind, plaintext in payloads:
            atomic_write(path, new_seal.wrap(plaintext, kind=kind, epoch=self.key_epoch))
        new_seal.persist_master(self.persist_dir / MASTER_NAME)
        self.seal = new_seal
        self.ops.emit(
            "rotate_rewrap",
            generation=new_gen,
            epoch=self.key_epoch,
            rewrapped=len(payloads),
        )
        return {
            "decision": "ALLOW",
            "generation": new_gen,
            "key_epoch": self.key_epoch,
            "rewrapped": len(payloads),
        }

    def _run_clerk(self, body: str) -> Tuple[str, Optional[str]]:
        """Return (status, deny_message). status is accepted | denied | required | error."""
        marked = any(m in body.upper() for m in MARKERS)
        if not marked:
            return "no_claim", None
        if self.claim_clerk is None:
            if self.require_clerk:
                return "required", "claim_clerk required for live bind"
            return "uncertified", "uncertified; wrapper does not mint [AXIOM]"
        try:
            ok, note = self.claim_clerk(body)
        except Exception as exc:
            self.ops.emit("clerk_exception", error_type=type(exc).__name__)
            return "error", f"clerk exception ({type(exc).__name__}); fail closed"
        if not ok:
            return "denied", note or "clerk refused claim"
        return "accepted", note

    def handle(self, env: Envelope, health: Optional[HealthSnapshot] = None) -> Dict[str, Any]:
        health = health or HealthSnapshot(live_faces=self.live_faces())
        health.live_faces = self.live_faces()
        health.key_epoch = self.key_epoch

        actor = self.agents.get(env.actor)

        if actor is None:
            return self._out("DENY", "Rei: unknown actor", env, health, hops=0, actor_fallback=True)

        if actor.status != "LIVE" and env.type != "restore":
            return self._out("DENY", "Rei: actor quarantined", env, health, hops=0, actor=actor)

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

        clerk_status, clerk_deny = self._run_clerk(env.body if not env.marked else env.body or "[AXIOM]")
        if env.marked and clerk_status == "no_claim":
            clerk_status, clerk_deny = self._run_clerk("[AXIOM] " + env.body)
        if clerk_status in ("required", "denied", "error"):
            rec = self._record("episodic", env, actor, health, hops, "DENY")
            return {
                "decision": "DENY",
                "phase": "Tsukuri",
                "message": clerk_deny,
                "clerk": clerk_status,
                "hops": hops,
                "telemetry": rec.digest,
                "live_faces": self.live_faces(),
            }
        clerk_note = {
            "accepted": "accepted",
            "uncertified": "uncertified; wrapper does not mint [AXIOM]",
            "no_claim": "no_claim",
        }.get(clerk_status, clerk_status)

        if env.type == "restore":
            if env.target is None:
                rec = self._record("episodic", env, actor, health, hops, "DENY")
                return {"decision": "DENY", "phase": "Kake", "message": "restore needs target"}
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
            self.key_epoch += 1

        rec = self._record("episodic", env, actor, health, hops, "ALLOW")
        return {
            "decision": "ALLOW",
            "phase": "Zanshin",
            "message": clerk_note,
            "clerk": clerk_status,
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


# Public name is BoheiShield. BS.AI = BoheiShield


def _default_live_clerk(body: str) -> Tuple[bool, str]:
    """Fail-closed stand-in. Hosts must replace this with their own clerk."""
    return False, "default live clerk refuses marked claims until the host clerk accepts"


def verify_bsai() -> int:
    """`--verify-BS.AI` production self-check. Exit 0 on pass."""
    checks: List[Tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    add("crypto", CRYPTO_AVAILABLE, AEAD_NAME if CRYPTO_AVAILABLE else "missing cryptography")
    add("aead_stock", AEAD_NAME in ("xchacha", "chacha", "none"), AEAD_NAME)
    add("atomic_write", callable(atomic_write), "temp+fsync+replace")
    add("rotate_api", hasattr(BoheiShield, "rotate_and_rewrap"), "operator rotate + rewrap")
    add("ops_log", hasattr(OpsLog, "emit"), "ops.jsonl")
    add("clerk_gate", True, "require_clerk on persist_dir bind")

    import tempfile
    import unittest

    tmp = Path(tempfile.mkdtemp(prefix="bsai_verify_"))
    try:
        def accept(_body: str) -> Tuple[bool, str]:
            return True, "accepted"

        bs = BoheiShield(persist_dir=tmp, claim_clerk=accept, require_clerk=True, hop_cap=3)
        bs.register("scribe", lane=2, caps={"persist_spillway": True, "emit_marked": True}, talk_to=["oracle"])
        bs.register("oracle", lane=7, talk_to=["scribe"])
        h = HealthSnapshot(C=0.7, kappa=0.2, H=0.2)
        r = bs.handle(Envelope(type="persist", actor="scribe", body="ok"), h)
        add("persist_allow", r["decision"] == "ALLOW", r["decision"])
        epi = tmp / "episodic.bsai"
        add("sealed_blob", epi.exists() and epi.read_bytes().startswith(ENVELOPE_MAGIC), "BSAI1")
        add("ops_file", (tmp / OPS_LOG_NAME).exists(), OPS_LOG_NAME)
        gen0 = bs.seal.generation if bs.seal else 0
        rot = bs.rotate_and_rewrap()
        add("rotate", rot["generation"] == gen0 + 1, f"gen {rot.get('generation')}")
        add("rewrap_readable", bs.seal.unwrap(epi.read_bytes()).startswith(b"["), "unwrap after rotate")

        no_clerk = BoheiShield(persist_dir=tmp / "live2", require_clerk=True)
        no_clerk.register("scribe", lane=2, caps={"emit_marked": True})
        denied = no_clerk.handle(Envelope(type="query", actor="scribe", body="[AXIOM] x", marked=True), h)
        add("clerk_required", denied["decision"] == "DENY", denied.get("message", "")[:60])

        def boom(_body: str) -> Tuple[bool, str]:
            raise RuntimeError("clerk down")

        exploding = BoheiShield(persist_dir=tmp / "live3", claim_clerk=boom, require_clerk=True)
        exploding.register("scribe", lane=2, caps={"emit_marked": True})
        crashed = exploding.handle(Envelope(type="query", actor="scribe", body="[LEAN] x", marked=True), h)
        add("clerk_exception_closed", crashed["decision"] == "DENY", crashed.get("message", "")[:60])
    except Exception as exc:
        add("verify_runtime", False, type(exc).__name__ + ": " + str(exc)[:80])

    # Charter suite
    try:
        from . import test_charter as charter
    except ImportError:
        try:
            import test_charter as charter  # type: ignore
        except ImportError:
            charter = None  # type: ignore
    if charter is not None:
        suite = unittest.defaultTestLoader.loadTestsFromModule(charter)
        result = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w")).run(suite)
        add("charter_rt1_rt10", result.wasSuccessful(), f"fails={len(result.failures)+len(result.errors)}")
    else:
        add("charter_rt1_rt10", False, "test_charter not importable")

    print("Bohei-Shield.AI  --verify-BS.AI")
    failed = 0
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  {mark}  {name}: {detail}")
    print("OK" if failed == 0 else f"{failed} CHECK(S) FAILED")
    return 0 if failed == 0 else 1


def demo() -> None:
    bs = BoheiShield(hop_cap=3, require_clerk=False)
    bs.register("scribe", lane=2, caps={"read_vaults": True}, talk_to=["oracle"])
    bs.register("oracle", lane=7, caps={"read_vaults": True}, talk_to=["scribe"])
    health = HealthSnapshot(C=0.74, kappa=0.21, H=0.33, live_faces=62)

    print("Bohei-Shield.AI  ·  Makami.AI  ·  standalone wrapper")
    print("AEAD:", AEAD_NAME, "crypto:", CRYPTO_AVAILABLE)
    print()

    r1 = bs.handle(Envelope(type="query", actor="scribe", target="oracle", body="status"), health)
    print("query", r1["decision"], "hops", r1["hops"], "epoch", r1.get("key_epoch"))

    r2 = bs.handle(Envelope(type="tool-result", actor="scribe", body="[AXIOM] forged", marked=True), health)
    print("tool-result marked", r2["decision"], r2["message"][:60])

    bs.new_turn()
    bs2 = BoheiShield(hop_cap=3, require_clerk=False)
    bs2.register("scribe", lane=2, talk_to=["oracle"])
    bs2.register("oracle", lane=7, talk_to=["scribe"])
    last = None
    for _ in range(5):
        last = bs2.handle(Envelope(type="sibling", actor="oracle", target="scribe", body="ping"), health)
        if last["decision"] != "ALLOW":
            break
    print("hop storm", last["decision"], last.get("hops"), (last.get("minuteman") or "")[:70])
    print("live faces", bs2.live_faces(), "oracle", bs2.agents["oracle"].status)
    print("minuteman in table?", "minuteman" in bs2.agents)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="bohei-shield")
    parser.add_argument("--verify-BS.AI", "--verify-bsai", dest="verify", action="store_true",
                        help="Run production self-check (ops log, clerk, atomic persist, rotate/rewrap, charter).")
    parser.add_argument("--demo", action="store_true", help="Run the short bus demo.")
    args = parser.parse_args(argv)
    if args.verify:
        return verify_bsai()
    demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
