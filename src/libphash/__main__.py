"""Run the command line: ``python -m libphash --help``."""

import sys

from ._cli import main

sys.exit(main(prog="python -m libphash"))
