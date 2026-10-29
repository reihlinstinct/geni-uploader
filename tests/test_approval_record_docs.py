"""Pin the approval-record doc so its safety claims cannot drift silently (#261)."""
import hashlib
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / 'docs' / 'approval-record.md'
# Update deliberately, in the same reviewed PR, whenever the doc changes.
EXPECTED_SHA256 = '36738450d46f2b3edc024b9e073a5b5b038a0f26afe70e80dca421f54e863eba'


def test_approval_record_doc_is_pinned():
    assert hashlib.sha256(DOC.read_bytes()).hexdigest() == EXPECTED_SHA256


def test_approval_record_doc_states_the_limits():
    text = DOC.read_text(encoding='utf-8')
    for claim in ('`authenticated: false`', '`post_permitted: false`', 'exactly two',
                  'no self-review', 'release blockers', '900'):
        assert claim in text
