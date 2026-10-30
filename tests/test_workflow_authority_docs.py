"""Pin docs reconciliation, not proof of live settings or permission."""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path,expected', [
    ('README.md', 'e9ed11bdf04b9a59735444a0c0d5e31ea0e3479876149d7a02567713deae494d'), ('docs/usage.md', '005a19793b3228abb393b43f5a6362cdc7a201213b11db9d51053372384862f9'),
    ('docs/privacy.md', '4d1e827bdeff1c59c970d86b415490aee799e5945196137e6ff315fc73e96c62'), ('PRIVACY.md', '4d1e827bdeff1c59c970d86b415490aee799e5945196137e6ff315fc73e96c62'),
    ('docs/workflow-authority.md', '4e217d8771ca19b67942552108bc6d1ad66575165d37a4e747675c1a907120c8')])
def test_workflow_authority_doc_whole_file_pin(path, expected):
    assert hashlib.sha256(' '.join((ROOT/path).read_text().split()).encode()).hexdigest() == expected
