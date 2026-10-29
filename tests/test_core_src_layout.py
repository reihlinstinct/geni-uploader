"""Core-cluster path and identity checks added without weakening old fixtures."""
import ast
import hashlib
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "parent_intent_model": ("intent", "518d93a0d952f3b2f657ee27f122779d84acaa640b46d33b781bd57ef86051a4"),
    "parent_adapter_contract": ("parent_contract", "da0e7483c96959df75a2599c1a976c6a493b5beecc4721243c1eaef58f020713"),
    "parent_snapshot": ("snapshot", "11874768bbc9abe021f64138c588393719d100f498340e257d46a1731624ead3"),
    "profile_outcome_model": ("outcome", "b52bffc26601526ce220b3f47371ad37683d4d89112e00c12cf8a056eb3e81dd"),
}


@pytest.mark.parametrize('legacy', MOVES)
def test_core_identity_and_intact_source(legacy, monkeypatch):
    target, before_hash = MOVES[legacy]
    canonical = importlib.import_module('geni_uploader.core.' + target)
    old = importlib.import_module(legacy)
    assert old is canonical
    marker = object()
    monkeypatch.setattr(old, 'digest', marker)
    assert canonical.digest is marker
    source = (ROOT / 'src/geni_uploader/core' / (target + '.py')).read_text()
    for name, (destination, _) in MOVES.items():
        source = source.replace('from geni_uploader.core.' + destination + ' import ',
                                'from ' + name + ' import ')
    if legacy == "profile_outcome_model":
        source = source.replace("from parent_intent_model import validate as validate_intent\n", "")
    assert hashlib.sha256(source.encode()).hexdigest() == before_hash
    for imports in [f'import {legacy}; import geni_uploader.core.{target} as canonical',
                    f'import geni_uploader.core.{target} as canonical; import {legacy}']:
        subprocess.run([sys.executable, '-c', imports + f'; assert {legacy} is canonical'],
                       cwd=ROOT, check=True, capture_output=True, text=True)


def test_all_runtime_callers_use_canonical_core_imports():
    paths = list(ROOT.glob('*.py')) + list((ROOT / 'src').rglob('*.py'))
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in MOVES, path
            if isinstance(node, ast.Import):
                assert all(alias.name not in MOVES for alias in node.names), path
