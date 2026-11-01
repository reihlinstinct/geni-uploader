"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.client import closed_parent as _implementation

sys.modules[__name__] = _implementation
