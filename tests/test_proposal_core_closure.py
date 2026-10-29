"""Complete proposal closure stays pure and keeps extracted definitions intact."""
import ast
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS = {
    "PROOFS": "53c8f6ea32ddeadaba0954523c859ece54cef452d8a98d3a891eef1cd0f8f1c3",
    "BLOCKERS": "a9e63ba84b1d4d1bfb18e1fa774edde8513a34eb06332eb3c52eaec09576d5e8",
    "proposal": "12c80413fde08d8147d148297b9ba23e011c941c38228df06969ead44854d85a",
    "verify_proposal": "528a572b1dcc61ba003113bb73471f0d3f1c5c4ba58ee6280aac8cb8c7445c02",
    "payloads": "fb63c8649e3548b75583b7c1d3aacdcb992785bcb854b2a91739a31cd5640eaf",
}


@pytest.mark.parametrize('module', ['proposal_review', 'proof_requirements'])
def test_extracted_definitions_byte_identical(module):
    path = ROOT / 'src/geni_uploader/core' / (module + '.py')
    source = path.read_text().splitlines(keepends=True)
    found = set()
    for node in ast.parse(''.join(source)).body:
        name = node.name if isinstance(node, ast.FunctionDef) else (
            node.targets[0].id if isinstance(node, ast.Assign) else '')
        if name in DEFINITIONS:
            found.add(name)
            assert hashlib.sha256(''.join(source[node.lineno-1:node.end_lineno]).encode(
            )).hexdigest() == DEFINITIONS[name]

    assert found == ({"PROOFS"} if module == "proof_requirements" else
                     {"payloads", "proposal", "verify_proposal", "BLOCKERS"})


def test_compatibility_names_are_the_same_objects():
    import human_parent_gate
    import parent_plan
    import parent_runner
    from geni_uploader.core import proof_requirements, proposal_review
    assert human_parent_gate.PROOFS is proof_requirements.PROOFS
    for name in ['proposal', 'verify_proposal', 'BLOCKERS']:
        assert getattr(parent_plan, name) is getattr(proposal_review, name)
    assert parent_runner.payloads is proposal_review.payloads


def test_recursive_proposal_import_closure_excludes_io_and_upward_layers():
    seen = set()
    def visit(name):
        if name in seen:
            return
        seen.add(name)
        path = ROOT / 'src' / Path(*name.split('.')).with_suffix('.py')
        for node in ast.walk(ast.parse(path.read_text())):
            modules = ([node.module] if isinstance(node, ast.ImportFrom)
                       else [alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [])
            for imported in modules:
                if imported.startswith('geni_uploader.'):
                    assert imported.startswith('geni_uploader.core.'), imported
                    visit(imported)
                else:
                    assert imported in {'copy', 're', 'datetime', 'hashlib', 'json',
                                        'sqlite3', 'unicodedata'}, imported
    visit('geni_uploader.core.proposal_review')
    visit('geni_uploader.core.proof_requirements')
    # sqlite is an existing people module dependency, not a call at import-time.
    assert seen == {'geni_uploader.core.proposal_review', 'geni_uploader.core.people',
                    'geni_uploader.core.proof_requirements'}
    tree = ast.parse((ROOT / 'parent_envelope.py').read_text())
    assert all(not isinstance(node, ast.ImportFrom) or node.module not in
               {'parent_plan', 'parent_runner', 'human_parent_gate'} for node in ast.walk(tree))
