"""Offline evidence package migration, all prior content fixtures unchanged."""
import ast
import hashlib
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "approval_record": ("approval", "e33fce32ae3e479ebb8dbfed2049afe7f73c82fa87af839a90cf8760433fb3b4"),
    "ciphertext_evidence": ("ciphertext", "61f1339557d8867231db26c84bdb8cab5a83c88da584383efb1966279b7e84b3"),
    "github_review_evidence": ("github_review", "c0f37f28cccdcafa8bbe4d2d109a920b1f6fbd5923fc3cae083489923c7ed093"),
    "workflow_content_contract": ("workflow_content", "a085345055d0f81198d3702368c63b616ac05baf88a1bdbb70e3ebe1c4cfce71"),
    "parent_evidence": ("parent", "4f015b9e8cee42a51f2913b541464f9a7353bfb3bd2f14cab764889a37bf8da9"),
    "profile_result": ("profile_result", "1dfc5c1d89afe9704ea1b146ac55ad260dbc697ca298ed03dc96cda91d396853"),
    "single_human_approval_record": ("single_human_approval", "e97fe42e8d5bb928404f25a7795160167f9e2ffd1a7fdf6f85f0edd0193cce16"),
}


def normalized_ast_hash(source):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in MOVES:
            node.module = 'geni_uploader.evidence.' + MOVES[node.module][0]
    first = next(i for i, node in enumerate(tree.body)
                 if isinstance(node, (ast.Import, ast.ImportFrom)))
    end = first
    while end < len(tree.body) and isinstance(tree.body[end], (ast.Import, ast.ImportFrom)):
        end += 1
    tree.body[first:end] = sorted(tree.body[first:end], key=ast.dump)
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode()).hexdigest()


@pytest.mark.parametrize('legacy', MOVES)
def test_evidence_identity_and_implementation(legacy, monkeypatch):
    target, before = MOVES[legacy]
    canonical = importlib.import_module('geni_uploader.evidence.' + target)
    old = importlib.import_module(legacy)
    assert old is canonical
    marker = object()
    monkeypatch.setattr(old, 'require', marker)
    assert canonical.require is marker
    assert normalized_ast_hash((ROOT / 'src/geni_uploader/evidence' /
                                (target + '.py')).read_text()) == before
    for imports in [f'import {legacy}; import geni_uploader.evidence.{target} as canonical',
                    f'import geni_uploader.evidence.{target} as canonical; import {legacy}']:
        subprocess.run([sys.executable, '-c', imports + f'; assert {legacy} is canonical'],
                       cwd=ROOT, check=True, capture_output=True, text=True)


def test_runtime_evidence_imports_are_canonical():
    for path in list(ROOT.glob('*.py')) + list((ROOT / 'src').rglob('*.py')):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in MOVES, path
            if isinstance(node, ast.Import):
                assert all(alias.name not in MOVES for alias in node.names), path
