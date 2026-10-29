"""Offline evidence package migration, all prior content fixtures unchanged."""
import ast
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOVES = {
    "approval_record": ("approval", "5f3ee84baaeb68b7bd7dc099321b02fe55acab0ce8ebdbb01f0fa22e156fdf12"),
    "ciphertext_evidence": ("ciphertext", "4ff764cbd65360ca308390f56a0939621f70aa96c1b16e2a072bc72166720ebe"),
    "github_review_evidence": ("github_review", "74689e9bda6e2c615935eb7da601ebef75e2c3b371255df46af6d63cae91db16"),
    "workflow_content_contract": ("workflow_content", "f1d9d7804d572db1d024904fbe460c97c581ce3a084ccad0f475c7676f2f8e62"),
    "parent_evidence": ("parent", "b51a48ddc47eebe79a158d960b6244573c3633bbe2ee444df39b5c7b1dd51818"),
    "profile_result": ("profile_result", "71778b73a5483f6efcce2e4aa475773bb0fac8c7db7dddfbe4d5fc0e722d9a0c"),
    "single_human_approval_record": ("single_human_approval", "42ca6e5f17e300e5a482b6e2a6df85632efbe83bf16825bbfef52fdf06e2762f"),
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
    def stable(node):
        if isinstance(node, ast.AST):
            return [type(node).__name__, [[key, stable(value)]
                    for key, value in ast.iter_fields(node)
                    if not (key == "type_params" and value == [])]]
        if isinstance(node, list):
            return [stable(value) for value in node]
        return [type(node).__name__, repr(node)]
    return hashlib.sha256(json.dumps(stable(tree), sort_keys=True).encode()).hexdigest()



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
