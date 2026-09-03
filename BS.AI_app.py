#!/usr/bin/env python3
"""Bohei-Shield.AI CLI. Use --verify-BS.AI for the production self-check."""
import sys
try:
    from wrapper import main
except ImportError:
    from bohei_shield.wrapper import main

if __name__ == "__main__":
    raise SystemExit(main())
