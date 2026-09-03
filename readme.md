# Bohei-Shield.AI

**Makami.AI** first public module. A multi-agent health wrapper.

It is **not** a language model and **not** a homemade cipher. This wrapper is the map you put in front of a stack of agents so one sick sibling cannot poison the bus.

Version **0.5.0** — live product hygiene on the v0.4 charter: structured ops log, required claim clerk on live bind, atomic persist, master-key rotation + rewrap.

## What it is

- Typed channels: `ingest | query | sibling | tool-result | persist | restore`
- Agent table with default-deny capabilities and `talk_to[]`
- Hop cap on same-turn Kake (graph cascade brake)
- Four-cache telemetry: axiomatic, structural, dynamic, episodic — **records, not field tiles**
- Structured ops log (`ops.jsonl`) — decisions, register, dissipate, persist, rotate. No secrets, no spillway bodies
- Hideo filter: circular override, closed-lane write, capability exceed, tool-result claiming operator status
- Minuteman: dissipate the actor, close the lane, **stand down**. There is no `minuteman` agent id (charter RT-10)
- Ukemi: `κ ≥ 0.85` or `H ≥ 0.90` freezes seals and epoch
- Quorum: fewer than 32 of 62 lanes live refuses new persist
- **Claim clerk is required** on a persist-dir / live bind. Marked claims without a host clerk are `DENY`. Clerk exceptions fail closed — they never crash the bus
- Atomic persist: write-temp → fsync → replace
- Optional AEAD envelope (`BSAI1`) over stock XChaCha20-Poly1305 or ChaCha20-Poly1305. Fail closed. No `INSECURE:` prefix
- Operator `rotate_and_rewrap()`: new master secret, bump generation, rewrap every `*.bsai`

Thermodynamic mapping is a **snapshot the host supplies** (`C`, `κ`, `H`, live faces, epoch). This module does not evolve a SIPR field.

## Install

```text
pip install cryptography    # required for persist, rotate, verify AEAD path
```

Clone this repo. No K-Dropz import.

```python
from wrapper import BoheiShield, Envelope, HealthSnapshot

def clerk(body: str):
    # Host implementation. Must not raise into the bus — wrapper still catches.
    return True, "accepted"

bs = BoheiShield(hop_cap=8, persist_dir="./bsai_state", claim_clerk=clerk)
bs.register("scribe", lane=2, caps={"read_vaults": True, "persist_spillway": True}, talk_to=["oracle"])
bs.register("oracle", lane=7, talk_to=["scribe"])

out = bs.handle(
    Envelope(type="query", actor="scribe", target="oracle", body="status"),
    HealthSnapshot(C=0.74, kappa=0.21, H=0.33),
)
print(out["decision"], out["telemetry"])
```

## Verify

```text
python wrapper.py --verify-BS.AI
python test_charter.py
python test_ops_hygiene.py
```

`--verify-BS.AI` checks AEAD availability, atomic write, required clerk, clerk-exception fail-closed, rotate + rewrap, ops log file, and RT-1…RT-10.

## Rotate

```python
bs.rotate_and_rewrap()   # operator only; refuses when seals are frozen
```

Confidentiality stays a reviewed AEAD. Rotation replaces the 32-byte master and rewraps on-disk envelopes. `key_epoch` remains the schedule counter; `generation` is the master generation.

## What this is not

- Not a trainable WLM, not a vision stack
- Not “entropic cryptography”
- Not a keyword denylist pretending to be a perimeter

## Bind later

A host should:

1. Pass `HealthSnapshot` from its own sensors
2. Pass a `claim_clerk` callable on any persist-dir / live bind
3. Never let this module write the host field

Makami.AI · product lock v0.5 · September 2026
