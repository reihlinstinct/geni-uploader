"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.evidence import profile_result as _implementation

sys.modules[__name__] = _implementation
