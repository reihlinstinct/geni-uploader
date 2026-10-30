"""Separately approved protected pilot. Not imported by the general uploader."""
import base64
import hashlib
import http.client
import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from geni_uploader.core.parent_contract import payload
from geni_uploader.core.people import Blocked, exact, require
from parent_probe import encrypt

LIMIT = 1024 * 1024
STAGES = frozenset(('setup', 'config', 'manifest', 'output', 'github_credential',
                    'encryption', 'private_source', 'credential', 'preflight',
                    'preflight_evidence', 'consume', 'send', 'ack', 'readback', 'final'))


class TransportStop(Blocked):
    """Fixed non-identifying diagnostics only; never response values or exceptions."""
    def __init__(self, code):
        require(code in ('transport_unavailable', 'response_oversize', 'response_deadline',
                         'response_status', 'response_redirect', 'response_malformed'))
        self.code = code
        super().__init__(code)


class Progress:
    def __init__(self):
        self.stage = 'setup'

    def enter(self, stage):
        require(stage in STAGES)
        self.stage = stage

FIELDS = ('id,guid,url,profile_url,first_name,middle_name,last_name,maiden_name,names,gender,'
          'public,is_alive,merge_pending,merged_into,unions')


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    require(type(raw) is bytes and len(raw) <= LIMIT)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class HTTPS:
    """Fixed host, bounded body, no redirects/proxy/refresh/retry or raw exceptions."""
    def __init__(self, host, token, *, github=False):
        require(host == ('api.github.com' if github else 'www.geni.com'))
        require(type(token) is str and re.fullmatch(r'[A-Za-z0-9._~-]{8,4096}', token))
        self.host, self.token, self.github = host, token, github
        self.calls, self.last, self.posted = 0, None, False

    def request(self, method, route, body=None):
        require(method in ('GET', 'POST') and type(route) is str and route.startswith('/'))
        require(not any(c in route for c in '\r\n#') and len(route) <= 2048)
        if not self.github:
            require(self.calls < 12)
            require((method == 'GET' and re.fullmatch(
                r'/api/(?:profile|profile-[0-9]{1,30}(?:/immediate-family)?|union-[0-9]{1,30})(?:\?fields=[A-Za-z_,]+&only_ids=true|\?only_ids=true)?', route))
                or (method == 'POST' and re.fullmatch(r'/api/profile-[0-9]{1,30}/add-parent', route)))
            if method == 'POST':
                require(not self.posted)
                self.posted = True
            if self.last is not None:
                time.sleep(max(0, 10 - (time.monotonic() - self.last)))
            self.calls += 1
            self.last = time.monotonic()
        client = None
        try:
            client = http.client.HTTPSConnection(self.host, port=443, timeout=20)
            headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json',
                       'User-Agent': 'single-parent-pilot', 'Content-Type': 'application/json'}
            if self.github:
                headers['X-GitHub-Api-Version'] = '2022-11-28'
            client.request(method, route, body=None if body is None else canonical(body),
                           headers=headers)
            response = client.getresponse()
            if not 200 <= response.status < 300:
                raise TransportStop('response_status')
            if response.getheader('Location') or response.getheader('Link'):
                raise TransportStop('response_redirect')
            # Per-read socket timeout is supplemented by a whole-response deadline.
            deadline = time.monotonic() + 30
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise TransportStop('response_deadline')
                chunk = response.read(min(65536, LIMIT + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > LIMIT:
                    raise TransportStop('response_oversize')
                if time.monotonic() >= deadline:
                    raise TransportStop('response_deadline')
                chunks.append(chunk)
            try:
                return decode(b''.join(chunks))
            except (Blocked, ValueError, TypeError, RecursionError):
                raise TransportStop('response_malformed') from None
        except TransportStop:
            raise
        except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
                http.client.HTTPException, subprocess.SubprocessError):
            raise TransportStop('transport_unavailable') from None
        finally:
            if client is not None:
                try:
                    client.close()
                except (OSError, http.client.HTTPException, subprocess.SubprocessError):
                    pass  # close failure cannot permit a second send


class PrivateGit:
    """Private immutable ref CAS, then encrypted annotated-tag receipts. No commit writes."""
    def __init__(self, client, repo, data_sha, owner):
        self.client = client
        self.prefix = '/repos/' + repo
        self.data_sha = data_sha
        self.marker = 'pilot-parent-consumed-v1-' + sha(owner.encode())

    def get(self, suffix):
        return self.client.request('GET', self.prefix + suffix)

    def load(self, path):
        repo = self.get('')
        require(repo.get('private') is True and repo.get('full_name') == self.prefix[7:])
        r = self.get('/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + self.data_sha)
        require(r.get('type') == 'file' and r.get('encoding') == 'base64'
                and type(r.get('size')) is int and 0 < r['size'] <= 65536)
        content = base64.b64decode(''.join(r['content'].split()), validate=True)
        require(len(content) == r['size'])
        return decode(content)

    def consume(self):
        # Atomic create, no update/delete/reset. Existing tag means STOP, even after failure.
        r = self.client.request('POST', self.prefix + '/git/refs', {
            'ref': 'refs/tags/' + self.marker, 'sha': self.data_sha})
        require(r.get('ref') == 'refs/tags/' + self.marker
                and r.get('object', {}).get('sha') == self.data_sha)
        r = self.get('/git/ref/tags/' + self.marker)
        require(r.get('object', {}).get('sha') == self.data_sha)

    def receipt(self, stage, ciphertext):
        require(stage in ('before', 'ack', 'final'))
        require(type(ciphertext) is bytes and ciphertext.startswith(b'age-encryption.org/v1\n')
                and len(ciphertext) <= LIMIT)
        message = 'Encrypted pilot evidence (age, base64)\n' + base64.b64encode(ciphertext).decode('ascii')
        name = self.marker + '-' + stage
        tag = self.client.request('POST', self.prefix + '/git/tags', {
            'tag': name, 'message': message, 'object': self.data_sha, 'type': 'commit'})
        tag_sha = tag.get('sha')
        require(type(tag_sha) is str and re.fullmatch(r'[a-f0-9]{40}', tag_sha))
        r = self.client.request('POST', self.prefix + '/git/refs', {
            'ref': 'refs/tags/' + name, 'sha': tag_sha})
        require(r.get('object', {}).get('sha') == tag_sha)
        require(self.get('/git/ref/tags/' + name).get('object', {}).get('sha') == tag_sha)
        check = self.get('/git/tags/' + tag_sha)
        require(check.get('message') == message and check.get('object', {}).get('sha') == self.data_sha)


def configuration(value):
    exact(value, ('schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
                  'recipient', 'allow_unknown_merge', 'accept_hidden_parent_risk',
                  'accept_private_create_risk', 'expires_at'))
    require(value['schema'] == 1 and type(value['schema']) is int)
    require(type(value['data_repo']) is str and re.fullmatch(
        r'[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_-]{1,100}', value['data_repo']))
    require(type(value['data_sha']) is str and re.fullmatch(r'[a-f0-9]{40}', value['data_sha']))
    require(type(value['data_path']) is str and re.fullmatch(
        r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.json', value['data_path'])
        and '..' not in value['data_path'])
    require(type(value['owner']) is str and re.fullmatch(r'profile-[0-9]{1,30}', value['owner']))
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['recipient']) is str and re.fullmatch(r'age1[0-9a-z]{58}', value['recipient']))
    require(type(value['allow_unknown_merge']) is bool)
    require(value['accept_hidden_parent_risk'] is True and value['accept_private_create_risk'] is True)
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2 ** 40)
    return value


def merge_clear(value, allow_unknown):
    require(type(value) is dict and 'error' not in value)
    known = 'merge_pending' in value or 'merged_into' in value
    if known:
        require(value.get('merge_pending') is False and value.get('merged_into') is None)
    else:
        require(allow_unknown)
    return 'known_clear' if known else 'UNKNOWN'


def get_profile(client, route):
    return client.request('GET', '/api/' + route + '?fields=' + FIELDS + '&only_ids=true')


def preflight(client, config):
    owner = config['owner']
    unknown = []
    for route in ('profile', owner):
        p = get_profile(client, route)
        require(p.get('id') == owner and ('unions' not in p or p['unions'] == []))
        unknown.append(merge_clear(p, config['allow_unknown_merge']))
        names = ' '.join(p.get(k, '') for k in ('first_name', 'middle_name', 'last_name'))
        require(all(w.casefold() in names.casefold().split() for w in config['expect_name'].split()))
    family = client.request('GET', '/api/' + owner + '/immediate-family?only_ids=true')
    require(type(family) is dict and set(family) <= {'focus', 'nodes'})
    require(type(family.get('focus')) is dict and family['focus'].get('id') == owner)
    unknown.append(merge_clear(family['focus'], config['allow_unknown_merge']))
    require(type(family.get('nodes')) is dict)
    # This pilot is only for a currently isolated root. Any observed relative/union blocks.
    require(set(family['nodes']) <= {owner})
    if owner in family['nodes']:
        require(family['nodes'][owner].get('id') == owner)
    for p in (family['focus'], family['nodes'].get(owner, {})):
        require('unions' not in p or p['unions'] == [])
    return {'observed_graph': 'isolated_root', 'merge_evidence': unknown,
            'hidden_parent_completeness': 'UNPROVED', 'request_count': 3}


def verify(client, config, created_id, expected):
    actual = get_profile(client, created_id)
    require(actual.get('id') == created_id)
    merge_clear(actual, config['allow_unknown_merge'])
    require(actual.get('public') is False and actual.get('is_alive') is True)
    require(actual.get('gender') == 'male')
    for key, val in expected.items():
        require(actual.get(key) == val)
    unions = actual.get('unions')
    require(type(unions) is list and len(unions) == 1 and type(unions[0]) is str
            and re.fullmatch(r'union-[0-9]{1,30}', unions[0]))
    union = client.request('GET', '/api/' + unions[0] + '?only_ids=true')
    require(union.get('id') == unions[0] and union.get('partners') == [created_id]
            and union.get('children') == [config['owner']])
    url = actual.get('profile_url')
    if url is not None:
        require(type(url) is str)
        parsed = urllib.parse.urlsplit(url)
        require(parsed.scheme == 'https' and parsed.netloc == 'www.geni.com'
                and not parsed.fragment)
    return {'object_id': created_id, 'vendor_url': url, 'profile': actual, 'union': union}


def execute(config, manifest, client, store, save, clock=time.time, progress=None):
    """Tests inject all effects. The protected action supplies the only live wiring."""
    progress = progress or Progress()
    progress.enter('config')
    config = configuration(config)
    require(clock() < config['expires_at'])
    progress.enter('manifest')
    exact(manifest, ('kind', 'target', 'creation_enabled', 'payload'))
    require(manifest['kind'] == 'offline_father_only_data_proposal'
            and manifest['creation_enabled'] is False and manifest['target'] == config['owner'])
    approved = payload(manifest['payload'])
    require(approved['gender'] == 'male' and approved['is_alive'] is True)
    report = {'schema': 1, 'mode': 'one_time_parent_pilot', 'data_sha': config['data_sha'],
              'data_path': config['data_path'], 'owner': config['owner'],
              'payload_sha256': sha(canonical(approved)), 'retry_allowed': False}
    progress.enter('preflight')
    report['preflight'] = preflight(client, config)
    require(clock() < config['expires_at'])
    # Save preflight evidence first, then consume globally before any POST.
    progress.enter('preflight_evidence')
    store.receipt('before', save(report))
    progress.enter('consume')
    store.consume()
    report['phase'] = 'UNCERTAIN'
    try:
        require(clock() < config['expires_at'])
        progress.enter('send')
        response = client.request('POST', '/api/' + config['owner'] + '/add-parent', approved)
        report['create_response'] = response
        require(type(response) is dict and 'error' not in response)
        created_id = response.get('id')
        require(type(created_id) is str and re.fullmatch(r'profile-[0-9]{1,30}', created_id)
                and created_id != config['owner'])
        report['object_id'] = created_id
        report['phase'] = 'ACKNOWLEDGED_NOT_VERIFIED'
        # Persist returned ID before any further vendor read. Failure forbids continuation/retry.
        progress.enter('ack')
        store.receipt('ack', save(report))
        require(clock() < config['expires_at'])
        progress.enter('readback')
        report['readback'] = verify(client, config, created_id, approved)
        report['phase'] = 'VERIFIED'
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
                http.client.HTTPException, subprocess.SubprocessError) as exc:
        report['stopped_stage'] = progress.stage
        report['failure_code'] = exc.code if isinstance(exc, TransportStop) else 'validation_or_storage'
        report['follow_up'] = 'GET-only reconciliation or separately approved repair; never retry create'
    progress.enter('final')
    store.receipt('final', save(report))
    if 'stopped_stage' in report:
        progress.enter(report['stopped_stage'])
    return report['phase']


def run(env, progress=None):
    progress = progress or Progress()
    require(env.get('PILOT_CONFIRM') == 'CREATE_ONE_PRIVATE_PARENT')
    require(env.get('GITHUB_RUN_ATTEMPT') == '1' and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_REPOSITORY') == 'reihlinstinct/geni-uploader'
            and env.get('GITHUB_REF') == 'refs/heads/master'
            and env.get('GITHUB_ACTOR') == 'reihlinstinct'
            and env.get('GITHUB_TRIGGERING_ACTOR') == 'reihlinstinct')
    progress.enter('config')
    config_raw = env.get('PILOT_CONFIG_JSON', '').encode()
    config = configuration(decode(config_raw))
    require(env.get('PILOT_CONFIG_SHA256') == sha(config_raw)
            and env.get('PILOT_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', '')))
    require(time.time() < config['expires_at'])
    # Encryption preflight before GitHub reads, marker creation, or any vendor call.
    progress.enter('encryption')
    encrypt(config['recipient'], b'pilot preflight')
    progress.enter('github_credential')
    github = HTTPS('api.github.com', env.get('FAMILY_TREE_PAT', ''), github=True)
    store = PrivateGit(github, config['data_repo'], config['data_sha'], config['owner'])
    progress.enter('private_source')
    manifest = store.load(config['data_path'])
    progress.enter('credential')
    client = HTTPS('www.geni.com', env.get('GENI_SECONDARY_ACCESS_TOKEN', ''))
    progress.enter('output')
    output = Path(env['PILOT_OUTPUT_DIR'])
    require(output.is_absolute() and not output.exists())
    output.mkdir(mode=0o700)
    def save(report):
        report = dict(report, executor_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'],
                      run_attempt=1, recorded_at=int(time.time()))
        ciphertext = encrypt(config['recipient'], canonical(report))
        # Local encrypted evidence survives even if remote receipt persistence fails.
        with (output / ('evidence-' + str(len(list(output.iterdir()))) + '.age')).open('xb') as f:
            os.chmod(f.name, 0o600)
            f.write(ciphertext)
            f.flush()
            os.fsync(f.fileno())
        return ciphertext
    return execute(config, manifest, client, store, save, progress=progress)


def main():
    progress = Progress()
    try:
        result = run(os.environ, progress)
        require(result == 'VERIFIED')
        print('pilot verification complete; encrypted evidence retained; no retry')
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
                http.client.HTTPException, subprocess.SubprocessError):
        print('pilot stopped at ' + progress.stage + '; inspect encrypted evidence; no retry or automatic repair')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
