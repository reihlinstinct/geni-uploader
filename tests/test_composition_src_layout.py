"""Offline composition migration identity and exact model structure guards."""
import importlib
from pathlib import Path

import pytest

from tests.test_evidence_src_layout import normalized_ast_hash

ROOT = Path(__file__).resolve().parents[1]
MOVES = {'father_once_simulation': ('core.father_once', '99b1513022a41665adf04d45b7d5f0a582016d7da74f555e55cb72a3768030df'), 'parent_runner': ('workflow.runner', 'e72a033599af3532b1d0c0a7f2fe007340c43e74c5acbbc90143fafc6a5fb73c'), 'father_executor_composition': ('workflow.father_executor', '78ac8e47648f5bce27f8ccebe7b65b70dbc2965ef30ed98f5156b8cfb1998032'), 'protected_father_job': ('workflow.protected_father_job', 'e91450e4bf10eb7cc29065fcadcdffc53dc60a4fca1e691465f2dec1bde9159e'), 'father_release_package': ('workflow.release_package', '08139c9aac5bc74f572d76f6046b5631445042c03530bd0cec60fc8d1c990f1c')}


@pytest.mark.parametrize('legacy', MOVES)
def test_composition_identity_and_intact_code(legacy, monkeypatch):
    target, before = MOVES[legacy]
    canonical = importlib.import_module('geni_uploader.' + target)
    assert importlib.import_module(legacy) is canonical
    if hasattr(canonical, 'require'):
        marker = object()
        monkeypatch.setattr(canonical, 'require', marker)
        assert importlib.import_module(legacy).require is marker
    source = (ROOT / 'src/geni_uploader' / Path(*target.split('.')).with_suffix('.py')).read_text()
    assert normalized_ast_hash(source) == before
