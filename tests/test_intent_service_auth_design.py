"""Pin design boundaries only, not actual authentication or storage guarantees."""
from pathlib import Path

import pytest

TEXT = (Path(__file__).resolve().parents[1] / 'docs/intent-service-auth-design.md').read_text()


@pytest.mark.parametrize(('section', 'phrases'), [
    ('Four distinct decisions', ['OIDC is NOT that approval', 'A merge is NOT a release',
                                'protected human environment review are mandatory']),
    ('Official identity contract', ['https://docs.github.com/en/actions/reference/security/oidc',
                                   'July 15, 2026', 'No wildcard or silent legacy fallback',
                                   'sub alone does NOT prove', 'no administrator bypass']),
    ('Proposed verifier, not implemented', ['Do not decode-and-trust a JWT', 'run_attempt 1',
                                          'issuer+jti', 'A short token lifetime alone is not one-use',
                                          'compromised approved runner']),
    ('Exact owner grant and permanent namespace', ['OPEN and release-blocking',
                                                  'not plan ID, connection label',
                                                  'BEFORE any possible POST',
                                                  'No automatic retry', 'merge, delete']),
    ('Encrypted evidence contract', ['BEFORE storage/upload', 'ciphertext only',
                                    'does not prove encryption', 'Object-store selection is OPEN',
                                    'consumed state survives', 'read-only grant']),
    ('Release verification matrix', ['wrong numeric owner/repo ID', 'ordinary verify from uncertain rejected',
                                    'They cannot prove cryptographic validation']),
])
def test_each_auth_section_keeps_its_own_release_limits(section, phrases):
    content = ' '.join(TEXT.split('## ' + section + '\n', 1)[1].split('\n## ', 1)[0].split())
    for phrase in phrases:
        assert phrase in content, (section, phrase)
