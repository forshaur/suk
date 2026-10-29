"""Allow ``python -m suk``."""

import sys

from suk.cli import main

if __name__ == "__main__":
    sys.exit(main())
