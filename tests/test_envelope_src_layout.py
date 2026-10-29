"""Envelope and local consumption retain behavior and import identity."""
import hashlib
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "parent_envelope": ("evidence.envelope", "c22af797a47e2149d0f5134e51a0fb28b996a95dcfbd8a4c8ad4e646119bc870"),
    "parent_consumption": ("workflow.consumption", "f4ae3ee384cedb89c5a90367bed792b96b34c8f8f665fe9f04f5d78262ed7d9f"),
}


@pytest.mark.parametrize('legacy', MOVES)
def test_identity_and_intact_source(legacy, monkeypatch):
    target, before = MOVES[legacy]
    canonical = importlib.import_module('geni_uploader.' + target)
    old = importlib.import_module(legacy)
    assert old is canonical
    marker = object()
    monkeypatch.setattr(old, 'require', marker)
    assert canonical.require is marker
    source = (ROOT / 'src/geni_uploader' / Path(*target.split('.')).with_suffix('.py')).read_text()
    source = source.replace('from geni_uploader.evidence.envelope import ',
                            'from parent_envelope import ')
    assert hashlib.sha256(source.encode()).hexdigest() == before
