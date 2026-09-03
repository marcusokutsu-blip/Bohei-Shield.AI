"""Bohei-Shield.AI — Makami.AI multi-agent health wrapper."""

try:
    from .wrapper import (
        AEAD_NAME, CRYPTO_AVAILABLE, LANES, QUORUM, HOP_CAP_DEFAULT,
        UKEMI_KAPPA, UKEMI_ENERGY, MESSAGE_TYPES, OPS_LOG_NAME,
        PersistClosed, CharterFail, ClerkRequired, HealthSnapshot,
        Envelope, AgentRow, TelemetryRecord, EnvelopeSeal, OpsLog,
        BoheiShield, BastionShield, atomic_write, verify_bsai, main,
    )
except ImportError:
    from wrapper import (
        AEAD_NAME, CRYPTO_AVAILABLE, LANES, QUORUM, HOP_CAP_DEFAULT,
        UKEMI_KAPPA, UKEMI_ENERGY, MESSAGE_TYPES, OPS_LOG_NAME,
        PersistClosed, CharterFail, ClerkRequired, HealthSnapshot,
        Envelope, AgentRow, TelemetryRecord, EnvelopeSeal, OpsLog,
        BoheiShield, BastionShield, atomic_write, verify_bsai, main,
    )

__all__ = [
    "AEAD_NAME", "CRYPTO_AVAILABLE", "LANES", "QUORUM", "HOP_CAP_DEFAULT",
    "UKEMI_KAPPA", "UKEMI_ENERGY", "MESSAGE_TYPES", "OPS_LOG_NAME",
    "PersistClosed", "CharterFail", "ClerkRequired", "HealthSnapshot",
    "Envelope", "AgentRow", "TelemetryRecord", "EnvelopeSeal", "OpsLog",
    "BoheiShield", "BastionShield", "atomic_write", "verify_bsai", "main",
]
__version__ = "0.5.0"
