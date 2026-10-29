"""Decision-record consistency only, not implementation or live authority."""
from hashlib import sha256
from pathlib import Path

import pytest

TEXT = (Path(__file__).resolve().parents[1] / 'docs/intent-storage-decisions.md').read_text()


@pytest.mark.parametrize(('section', 'phrases'), [
    ('Decision 1: protected job, immutable private approval record',
     ['Do not create a new approval signing key/service', 'not owner consent',
      'remains a release blocker', 'No automatic interpretation of chat approval phrases']),
    ('Decision 2: bounded ciphertext in existing private data storage',
     ['existing PRIVATE data repository', 'No public artifacts', 'No new object-store account',
      '1 MiB ciphertext per object and 8 MiB cumulative ciphertext',
      'Read back the remote blob and verify digest', 'No plaintext fallback']),
    ('Permanent intent is independent', ['Permanent owner-global consumption',
                                        'never clears intent', 'No retry, refresh, delete, merge']),
    ('Free-only execution boundary and tradeoffs', ['private Actions', 'STOP and ask',
                                                  'Free allowance is not a hard no-spending guarantee']),
    ('Remaining release work', ['exact private father payload/risk/run approval',
                               'This record supplies none of these permissions']),
])
def test_each_decision_keeps_its_own_boundary(section, phrases):
    part = ' '.join(TEXT.split('## ' + section + '\n', 1)[1].split('\n## ', 1)[0].split())
    for phrase in phrases:
        assert phrase in part, (section, phrase)


@pytest.mark.parametrize(('section', 'claim'), [
    ('Decision 1: protected job, immutable private approval record',
     "Use the public tool repository's standard GitHub-hosted runner for the eventual executor."),
    ('Decision 1: protected job, immutable private approval record',
     'Require a separate protected human approval job and an immutable exact private approval record.'),
    ('Decision 2: bounded ciphertext in existing private data storage',
     ('These conservative design caps need release validation with actual schema/encryption overhead; '
     'never truncate evidence to fit or quietly raise the cap.')),
    ('Decision 2: bounded ciphertext in existing private data storage',
     'immutable Git blob ID and commit hash'),
    ('Decision 2: bounded ciphertext in existing private data storage',
     'no private-repository Actions job.'),
])
def test_core_decision_claims_are_individually_required(section, claim):
    part = ' '.join(TEXT.split('## ' + section + '\n', 1)[1].split('\n## ', 1)[0].split())
    assert claim in part


def test_permanent_separation_and_every_release_blocker():
    permanent = ' '.join(TEXT.split('## Permanent intent is independent\n', 1)[1]
                         .split('\n## ', 1)[0].split())
    assert ('Permanent owner-global consumption belongs in the separately approved shared '
            'Durable Object state, not in artifacts or Git evidence retention alone.') in permanent
    release = ' '.join(TEXT.split('## Remaining release work\n', 1)[1].split())
    for blocker in (
        'Authenticated exact approval-record creation/review',
        'live issuer/subject and claim shape verification',
        'reviewed private writer access',
        'approved permanent DO namespace/authentication',
        'ciphertext serialization/retention/remote verification',
        'actual one-shot secondary HTTP adapter',
        'readback/reconciliation', '#244 provenance',
        'protected environment audit', 'immutable release pins', 'named release approval',
        'Then exact private father payload/risk/run approval and protected human gate.',
        'This record supplies none of these permissions or deployed capabilities.',
    ):
        assert blocker in release


# Lock every reviewed decision sentence, not only selected phrases. This is a
# textual approval pin, NOT behavioral proof. Intentional doc changes require
# explicit review of this expected digest, not automatic fixture regeneration.
SECTION_DIGESTS = {'Decision 1: protected job, immutable private approval record': '7ac4d75070764b46948b507252bcb9cf1b56146724cc7a82b36bbb73b2eb692a', 'Decision 2: bounded ciphertext in existing private data storage': '07a4bd3f04cb7c239650f8cccc513f7029fe68138b5df0916f2c8814c1d9da99', 'Permanent intent is independent': '22632543e8fed4a7507110e4d2c4ee7424807a26d3be19774b0d94b52c6b5231', 'Free-only execution boundary and tradeoffs': 'ffe093e18886f9fa73513a2377098c1047c2e172b7d36dff9e04bdee070d6e24', 'Remaining release work': '82917198851256de42a90484becbd3fce7562da25357bf66fe613f9b8a31d9ff'}


@pytest.mark.parametrize(('section', 'expected'), SECTION_DIGESTS.items())
def test_entire_reviewed_section_sentence_pin(section, expected):
    part = ' '.join(TEXT.split('## ' + section + '\n', 1)[1].split('\n## ', 1)[0].split())
    assert sha256(part.encode()).hexdigest() == expected


def test_whole_reviewed_document_including_title_date_and_preamble():
    # Normalized whole-file approval pin, not runtime or authority proof.
    assert sha256(' '.join(TEXT.split()).encode()).hexdigest() == 'b8c348d519bad325575cd0f70069c7722401f04d5c41074921414cac09a46161'
