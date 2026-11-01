"""Temporary import-identity facade; install the project before running callers."""
import sys

# In the runtime image the package lives at /opt/pkg (ENV PYTHONPATH there).
# Insert it explicitly so a caller overriding PYTHONPATH cannot shadow it;
# the path is absent in a checkout, where src/ resolves the package (#643).
sys.path.insert(0, '/opt/pkg')

from geni_uploader.client import cli_spec as _implementation

sys.modules[__name__] = _implementation
