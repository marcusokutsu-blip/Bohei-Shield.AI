# Bastion-Shield.AI

**Makami.AI** first public module. A multi-agent health wrapper.

It is **not** a language model, **not** a homemade cipher, and **not** Kintsugi-Dropz. Those stay private while they train. This wrapper is the map you put in front of a stack of agents so one sick sibling cannot poison the bus.

## What it is

- Typed channels: `ingest | query | sibling | tool-result | persist | restore`
- Agent table with default-deny capabilities and `talk_to[]`
- Hop cap on same-turn Kake (graph cascade brake)
- Four-cache telemetry in the same split as a four-vault memory economy: axiomatic, structural, dynamic, episodic — **records, not field tiles**
- Hideo filter: circular override, closed-lane write, capability exceed, tool-result claiming operator status
- Minuteman: dissipate the actor, close the lane, **stand down**. There is no `minuteman` agent id (charter RT-10)
- Ukemi: `κ ≥ 0.85` or `H ≥ 0.90` freezes seals and epoch
- Quorum: fewer than 32 of 62 lanes live refuses new persist
- Optional AEAD envelope (`BSAI1`) over stock XChaCha20-Poly1305 or ChaCha20-Poly1305. Fail closed. No `INSECURE:` prefix

Thermodynamic mapping is a **snapshot the host supplies** (`C`, `κ`, `H`, live faces, epoch). This module does not evolve a SIPR field.

## Install

```text
pip install cryptography    # optional; persist refuses without it
```

Drop the `bastion_shield/` folder into a repo or a Cursor project. No K-Dropz import.

```python
from bastion_shield import BastionShield, Envelope, HealthSnapshot

bs = BastionShield(hop_cap=8)
bs.register("scribe", lane=2, caps={"read_vaults": True}, talk_to=["oracle"])
bs.register("oracle", lane=7, talk_to=["scribe"])

out = bs.handle(
    Envelope(type="query", actor="scribe", target="oracle", body="status"),
    HealthSnapshot(C=0.74, kappa=0.21, H=0.33),
)
print(out["decision"], out["telemetry"])
```

## Demo and charter

```text
python -m bastion_shield.wrapper
python -m bastion_shield.test_charter
```

Charter tests are RT-1 … RT-10 from the locked spec: residue in the KDF, phase/occupancy handled by epoch+kind headers, closed-lane writes, untyped bus, viral persist after quarantine, lean audit, fail-closed persist, tool-result injection, hop cascade / quorum freeze, standing Minuteman forbidden.

## What this is not

- Not Kintsugi-Dropz, not a trainable WLM, not a vision stack
- Not “entropic cryptography.” Confidentiality is a reviewed AEAD. The proprietary piece is **binding and scheduling**: epoch, kind, occupancy, health halt
- Not a keyword denylist pretending to be a perimeter

## Bind later

A host (K-Dropz or anything else) should:

1. Pass `HealthSnapshot` from its own sensors
2. Optionally pass a `claim_clerk` callable; the wrapper will not mint `[AXIOM]`
3. Never let this module write the host field

Makami.AI · planning lock v0.4 · August 2026
