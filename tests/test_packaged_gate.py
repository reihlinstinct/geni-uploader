"""Always-closed gate uses packaged resource, never a checkout-relative path."""
import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gate_implementation_and_identity():
    import human_parent_gate
    from geni_uploader.workflow import release_gate
    assert human_parent_gate is release_gate
    path = ROOT / 'src/geni_uploader/workflow/release_gate.py'
    source = path.read_text().splitlines(keepends=True)
    node = next(n for n in ast.parse(''.join(source)).body if isinstance(n, ast.FunctionDef))
    digest = hashlib.sha256(''.join(source[node.lineno-1:node.end_lineno]).encode()).hexdigest()
    assert digest == 'be1a6e5d212456a2683abe49ffc8bc9603c1800e0e5b178796b0300c2af78bb6'
    assert release_gate.CONTRACT.read_bytes() == (
        ROOT / 'docs/human-parent-release-gates.json').read_bytes()
    assert '__file__' not in path.read_text()
