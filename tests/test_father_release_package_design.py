"""Design checkpoint does not release production effects."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_design_preserves_closed_gate_and_uninstalled_draft():
    gate = (ROOT / 'oauth-bootstrap/father-release-gate.mjs').read_text()
    assert "throw Error('father live executor unreleased')" in gate
    assert not (ROOT / '.github/workflows/father-run-workflow-draft.yml').exists()
    draft = (ROOT / 'docs/father-run-workflow-draft.yml').read_text()
    assert 'exit 1' in draft
    doc = ' '.join((ROOT / 'docs/father-release-package-design.md').read_text().split())
    for requirement in ('NEW father-only Worker', 'NEW SQLite', 'No account change',
                        'not this', 'Instinct', 'Review deployments', 'GET only'):
        assert requirement in doc
