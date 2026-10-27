"""Execute synthetic Safari parser regressions when Node is available."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_safari_parser_node_regressions():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable; synthetic Safari parser suite not executed")
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, str(root / "tools/safari-token/test-extract.js")],
                   check=True, timeout=20)
