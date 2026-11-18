"""Entrypoint direto do Robô Monitor & Indexador Oficial (RevTributaria)."""

from __future__ import annotations

import sys

from src.automation.sync_job import main

if __name__ == "__main__":
    sys.exit(main())
