"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.workflow import secondary_probe as _implementation

sys.modules[__name__] = _implementation

if __name__ == '__main__':
    raise SystemExit(_implementation.main())
