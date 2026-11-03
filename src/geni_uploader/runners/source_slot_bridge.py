"""Fixed secondary-to-source environment transfer. No Geni calls or dispatch."""
import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

import geni_uploader.runners.protected_source_approval as source

ENV = 'environments/father-create'
SRC = 'actions/secrets/GENI_SECONDARY_ACCESS_TOKEN'
DEST = ENV + '/secrets/GENI_ACCESS_TOKEN'
WORKFLOW = '.github/workflows/source-slot-bridge.yml'


def execute(env, request, seal):
    for key, value in (('GITHUB_REPOSITORY', source.REPO), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                       ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_ACTOR', 'reihlinstinct'),
                       ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'), ('GITHUB_RUN_ATTEMPT', '1'),
                       ('BRIDGE_CONFIRM', 'COPY_SECONDARY_TO_SOURCE_ENV')):
        source.require(env.get(key) == value)
    sha = env.get('BRIDGE_EXECUTOR_SHA', '')
    source.require(re.fullmatch(r'[a-f0-9]{40}', sha) and sha == env.get('GITHUB_SHA'))
    run = env.get('GITHUB_RUN_ID', '')
    source.require(re.fullmatch(r'[1-9][0-9]{0,19}', run))
    meta = request('GET', 'actions/runs/' + run)
    source.require(meta['head_sha'] == sha and meta['run_attempt'] == 1
                   and meta['path'] == WORKFLOW and meta['head_branch'] == 'master'
                   and meta['event'] == 'workflow_dispatch'
                   and meta['actor']['login'] == meta['triggering_actor']['login'] == 'reihlinstinct')
    protection = request('GET', ENV)
    source.require(protection['can_admins_bypass'] is False
                   and {x['type'] for x in protection['protection_rules']} == {'required_reviewers', 'branch_policy'}
                   and len(protection['protection_rules']) == 2)
    reviewer = next(x for x in protection['protection_rules'] if x['type'] == 'required_reviewers')
    source.require(reviewer['prevent_self_review'] is True and len(reviewer['reviewers']) == 1
                   and reviewer['reviewers'][0]['reviewer']['login'] == 'reihl')
    branches = request('GET', ENV + '/deployment-branch-policies')
    source.require(branches['total_count'] == 1 and branches['branch_policies'][0]['name'] == 'master'
                   and branches['branch_policies'][0]['type'] == 'branch')
    secrets = request('GET', ENV + '/secrets?per_page=100')
    source.require(secrets['total_count'] < 100 and len(secrets['secrets']) == secrets['total_count']
                   and 'GENI_SECONDARY_ACCESS_TOKEN' not in {x['name'] for x in secrets['secrets']})
    before = request('GET', SRC)
    source.require(before['name'] == 'GENI_SECONDARY_ACCESS_TOKEN'
                   and before['updated_at'] == env.get('BRIDGE_SOURCE_UPDATED_AT')
                   and re.fullmatch(r'[0-9TZ:-]{20}', before['updated_at']))
    value = env.get('BRIDGE_SOURCE_VALUE', '')
    source.require(type(value) is str and 0 < len(value) <= 65536)
    key = request('GET', ENV + '/secrets/public-key')
    source.require(len(base64.b64decode(key['key'], validate=True)) == 32)
    cipher = seal(value, key['key'])
    source.require(type(cipher) is str and len(base64.b64decode(cipher, validate=True)) == len(value.encode()) + 48)
    # Recheck source metadata immediately before one destination write.
    source.require(request('GET', SRC) == before)
    prior = request('GET', DEST)
    source.require(prior is None or prior.get('name') == 'GENI_ACCESS_TOKEN')
    request('PUT', DEST, {'encrypted_value': cipher, 'key_id': key['key_id']})
    after = request('GET', DEST)
    source.require(after['name'] == 'GENI_ACCESS_TOKEN'
                   and type(after['updated_at']) is str
                   and re.fullmatch(r'[0-9TZ:-]{20}', after['updated_at'])
                   and (prior is None or after['updated_at'] != prior.get('updated_at')))
    return True


def transport(token, method, path, body=None):
    reads = {ENV, ENV + '/deployment-branch-policies', ENV + '/secrets?per_page=100',
             ENV + '/secrets/public-key', SRC, DEST}
    source.require((method == 'GET' and (path in reads or re.fullmatch(r'actions/runs/[1-9][0-9]{0,19}', path)))
                   or method == 'PUT' and path == DEST)
    req = urllib.request.Request('https://api.github.com/repos/' + source.REPO + '/' + path,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'},
        data=json.dumps(body).encode() if body is not None else None, method=method)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args):
            raise source.Blocked()
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            data = response.read(1_000_000)
            return json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        if method == 'GET' and path == DEST and exc.code == 404:
            return None
        raise


def seal(value, public):
    result = subprocess.run(['node', 'oauth-bootstrap/source-slot-seal.mjs'],
        input=json.dumps({'value': value, 'public': public}).encode(), capture_output=True, check=True,
        env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')})
    return result.stdout.decode().strip()


def main():
    try:
        env = os.environ
        execute(env, lambda method, path, body=None: transport(env['BRIDGE_WRITER'], method, path, body), seal)
        print('fixed-slot transfer complete; separate source plan still required')
        return 0
    except Exception:  # noqa: BLE001 - no external or credential output
        print('fixed-slot transfer stopped; no retry')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
