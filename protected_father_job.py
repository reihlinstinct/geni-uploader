"""Temporary import-identity facade; install the project before running callers."""
import sys

from geni_uploader.workflow import protected_father_job as _implementation

sys.modules[__name__] = _implementation
