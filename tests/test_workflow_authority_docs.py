"""Pin docs reconciliation, not proof of live settings or permission."""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path,expected', [
    ('README.md', '337eb06e4ff5711d5f949f29e43346b8c5dc6dfbf8423bbc9b5985cf1569d175'), ('docs/usage.md', '6685074d5ae9118b7c7150060a93bf37d083b966ba5500a64c546c67dba3caad'),
    ('docs/privacy.md', '4d1e827bdeff1c59c970d86b415490aee799e5945196137e6ff315fc73e96c62'), ('PRIVACY.md', '4d1e827bdeff1c59c970d86b415490aee799e5945196137e6ff315fc73e96c62'),
    ('docs/workflow-authority.md', '4e217d8771ca19b67942552108bc6d1ad66575165d37a4e747675c1a907120c8')])
def test_workflow_authority_doc_whole_file_pin(path, expected):
    assert hashlib.sha256(' '.join((ROOT/path).read_text().split()).encode()).hexdigest() == expected
