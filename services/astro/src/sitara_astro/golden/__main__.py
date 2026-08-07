"""Entry point: python -m sitara_astro.golden <command>"""

import sys

from sitara_astro.golden.cli import main

if __name__ == "__main__":
    sys.exit(main())
