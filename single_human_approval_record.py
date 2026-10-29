"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.evidence import single_human_approval as _implementation

sys.modules[__name__] = _implementation
