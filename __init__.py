"""Bohei-Shield.AI — Makami.AI multi-agent health wrapper."""

from .wrapper import (
    AEAD_NAME,
    CRYPTO_AVAILABLE,
    LANES,
    QUORUM,
    HOP_CAP_DEFAULT,
    UKEMI_KAPPA,
    UKEMI_ENERGY,
    MESSAGE_TYPES,
    PersistClosed,
    CharterFail,
    HealthSnapshot,
    Envelope,
    AgentRow,
    TelemetryRecord,
    EnvelopeSeal,
    BastionShield,
)

__all__ = [
    "AEAD_NAME",
    "CRYPTO_AVAILABLE",
    "LANES",
    "QUORUM",
    "HOP_CAP_DEFAULT",
    "UKEMI_KAPPA",
    "UKEMI_ENERGY",
    "MESSAGE_TYPES",
    "PersistClosed",
    "CharterFail",
    "HealthSnapshot",
    "Envelope",
    "AgentRow",
    "TelemetryRecord",
    "EnvelopeSeal",
    "BoheiShield",
]
__version__ = "0.4.0"
