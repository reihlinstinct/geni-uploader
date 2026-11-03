"""Temporary import-identity facade; install the project before running callers."""
import sys
from pathlib import Path

# In the runtime image the package lives at /opt/pkg (ENV PYTHONPATH there).
# In a checkout it lives at src/; insert both so host-run scripts that
# import this facade without installing the project still resolve it.
sys.path.insert(0, '/opt/pkg')
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from geni_uploader.runners import household_relationship_read as _implementation

sys.modules[__name__] = _implementation
