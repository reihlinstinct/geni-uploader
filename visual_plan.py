"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.presentation import visual_plan as _implementation

sys.modules[__name__] = _implementation

if __name__ == '__main__':
    raise SystemExit(_implementation.main())
