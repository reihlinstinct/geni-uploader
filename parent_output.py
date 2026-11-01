"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.core import parent_output as _implementation

sys.modules[__name__] = _implementation
