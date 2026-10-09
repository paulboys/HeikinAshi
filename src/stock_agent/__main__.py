"""Entry point for ``python -m stock_agent``."""

from __future__ import annotations

import sys

from stock_agent.cli import main

if __name__ == "__main__":
    sys.exit(main())
