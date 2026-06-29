"""Entry point for ``python -m jetson_orin``."""

from __future__ import annotations

import sys

from jetson_orin.cli import main

if __name__ == "__main__":
    sys.exit(main())
