"""Allow `python -m prompt_registry.mcp`."""

import sys

from .entry import main

if __name__ == "__main__":
    sys.exit(main())
