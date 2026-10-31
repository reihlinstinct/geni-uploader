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
                    'encryption', 'private_source', 'recovery', 'credential', 'preflight',
                    'preflight_evidence', 'consume', 'send', 'ack', 'readback', 'final'))


class TransportStop(Blocked):
    """Fixed non-identifying diagnostics only; never response values or exceptions."""
    def __init__(self, code, *, evidence=None):
        require(code in ('transport_unavailable', 'response_oversize', 'response_deadline',
                         'response_status', 'response_redirect', 'response_malformed'))
        self.code = code
        self.evidence = evidence or {}
        super().__init__(code)


class Progress:
    def __init__(self):
        self.stage = 'setup'
        self.trace = None
        self.started = None

    def enable_debug(self):
        self.trace = []
        self.started = time.monotonic()
        self.enter(self.stage)

    def enter(self, stage):
        require(stage in STAGES)
        self.stage = stage
        if self.trace is not None and len(self.trace) < 64:
            elapsed = max(0, min(86400000, int((time.monotonic() - self.started) * 1000)))
            self.trace.append({'stage': stage, 'elapsed_ms': elapsed})

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
    def __init__(self, host, token, *, github=False, capture_failure=False):
        require(host == ('api.github.com' if github else 'www.geni.com'))
        require(type(token) is str and re.fullmatch(r'[A-Za-z0-9._~-]{8,4096}', token))
        self.capture_failure = capture_failure
        self.host, self.token, self.github = host, token, github
        self.calls, self.last, self.posted = 0, None, False

    def vendor_failure(self, response):
        # Structural diagnostics only. Never retain arbitrary headers or raw response text.
        evidence = {}
        content_type = response.getheader('Content-Type')
        media = content_type.split(';', 1)[0].strip().lower() if type(content_type) is str else ''
        evidence['body_media'] = (media if media in (
            'application/json', 'text/html', 'text/plain') else 'other' if media else 'absent')
        for field in ('Limit', 'Remaining', 'Window'):
            value = response.getheader('X-API-Rate-' + field)
            valid = type(value) is str and re.fullmatch(r'[0-9]{1,10}', value)
            evidence['geni_rate_' + field.lower() + '_state'] = (
                'absent' if value is None else 'numeric' if valid else 'invalid')
            if valid:
                evidence['geni_rate_' + field.lower()] = int(value)
        retry = response.getheader('Retry-After')
        valid_retry = type(retry) is str and re.fullmatch(r'[0-9]{1,10}', retry)
        evidence['retry_after_state'] = (
            'absent' if retry is None else 'numeric' if valid_retry else 'other')
        if valid_retry:
            evidence['retry_after_seconds'] = int(retry)
        evidence['request_id_present'] = any(response.getheader(k) is not None for k in (
            'X-Request-ID', 'X-Correlation-ID'))
        evidence['body_parse'] = 'read_error'
        try:
            raw = response.read(4097)
            evidence['body_bytes_observed'] = len(raw)
            evidence['body_over_cap'] = len(raw) > 4096
            if len(raw) > 4096:
                evidence['body_parse'] = 'over_cap'
                return evidence
            if not raw:
                evidence['body_parse'] = 'empty'
                return evidence
            try:
                decoded = decode(raw)
            except (Blocked, ValueError, TypeError, RecursionError):
                evidence['body_parse'] = 'invalid_json'
                return evidence
            evidence['body_parse'] = 'json'
            error = decoded.get('error') if type(decoded) is dict else None
            evidence['error_shape'] = (
                'object' if type(error) is dict else 'other' if type(decoded) is dict
                and 'error' in decoded else 'absent' if type(decoded) is dict else 'non_object')
            if type(error) is dict:
                for key in ('type', 'message'):
                    value = error.get(key)
                    if type(value) is str:
                        value = value.replace(self.token, '[REDACTED]')
                        value = re.sub(r'https?://[^\s]+', '[URL]', value)
                        evidence['geni_error_' + key] = ''.join(
                            c for c in value if c.isprintable())[:256]
        except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError,
                AttributeError, http.client.HTTPException):
            pass  # The original status remains available even if capture fails.
        return evidence

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
                evidence = {}
                if self.capture_failure:
                    evidence['http_status'] = response.status
                    if not self.github:
                        evidence.update(self.vendor_failure(response))
                    if self.github:
                        def bounded(value):
                            return ''.join(c for c in value.replace(self.token, '[REDACTED]')
                                           if c.isprintable())[:256]
                        hint = response.getheader('X-Accepted-GitHub-Permissions')
                        if type(hint) is str:
                            evidence['github_permissions_hint'] = bounded(hint)
                        try:
                            raw = response.read(4097)
                            if len(raw) <= 4096:
                                message = decode(raw).get('message')
                                if type(message) is str:
                                    evidence['github_message'] = bounded(message)
                        except (Blocked, OSError, ValueError, TypeError, AttributeError,
                                http.client.HTTPException):
                            pass  # original status must survive malformed error content
                raise TransportStop('response_status', evidence=evidence)
            # 201 creation metadata is not a redirect. Never follow its value.
            created_metadata = (self.github and method == 'POST' and response.status == 201
                and re.fullmatch(r'/repos/[A-Za-z0-9_-]{1,100}/[A-Za-z0-9_-]{1,100}/git/(?:tags|refs)',
                                 route))
            if response.getheader('Link') or (response.getheader('Location')
                                              and not created_metadata):
                raise TransportStop('response_redirect', evidence=(
                    {'http_status': response.status,
                     'location_present': bool(response.getheader('Location')),
                     'link_present': bool(response.getheader('Link'))}
                    if self.capture_failure else None))
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
        return decode(self.load_bytes(path, self.data_sha))

    def load_bytes(self, path, commit):
        repo = self.get('')
        require(repo.get('private') is True and repo.get('full_name') == self.prefix[7:])
        r = self.get('/contents/' + urllib.parse.quote(path, safe='/') + '?ref=' + commit)
        require(r.get('type') == 'file' and r.get('encoding') == 'base64'
                and type(r.get('size')) is int and 0 < r['size'] <= 65536)
        content = base64.b64decode(''.join(r['content'].split()), validate=True)
        require(len(content) == r['size'])
        return content

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
    require(type(value) is dict)
    recovery = ('recovery',) if 'recovery' in value else ()
    exact(value, (*recovery, 'schema', 'data_repo', 'data_sha', 'data_path', 'owner', 'expect_name',
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
    if recovery:
        recovery_config(value['recovery'])
    return value


def recovery_config(r):
    exact(r, ('attempt_id', 'run_id', 'attestation_sha', 'attestation_path',
              'attestation_digest', 'ciphertext_digest', 'report_digest', 'accept_uncertainty'))
    require(type(r['attempt_id']) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{7,47}', r['attempt_id']))
    require(type(r['run_id']) is str and re.fullmatch(r'[0-9]{1,20}', r['run_id']))
    require(type(r['attestation_sha']) is str and re.fullmatch(r'[a-f0-9]{40}', r['attestation_sha']))
    require(type(r['attestation_path']) is str and re.fullmatch(
        r'(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.json', r['attestation_path'])
        and '..' not in r['attestation_path'])
    for key in ('attestation_digest', 'ciphertext_digest', 'report_digest'):
        require(type(r[key]) is str and re.fullmatch(r'[a-f0-9]{64}', r[key]))
    require(r['accept_uncertainty'] is True)
    return r


def admit_recovery(store, c, manifest):
    """Owner-reviewed local decryption attestation, not an age proof in this runner."""
    r = recovery_config(c['recovery'])
    raw = store.load_bytes(r['attestation_path'], r['attestation_sha'])
    require(sha(raw) == r['attestation_digest'])
    a = decode(raw)
    exact(a, ('schema', 'kind', 'run_id', 'ciphertext_b64', 'report', 'accept_uncertainty'))
    require(a['schema'] == 1 and type(a['schema']) is int
            and a['kind'] == 'locally_decrypted_reconcile_attestation'
            and a['accept_uncertainty'] is True and a['run_id'] == r['run_id'])
    require(type(a['ciphertext_b64']) is str)
    cipher = base64.b64decode(a['ciphertext_b64'], validate=True)
    require(cipher.startswith(b'age-encryption.org/v1\n') and sha(cipher) == r['ciphertext_digest'])
    report = a['report']
    require(type(report) is dict and sha(canonical(report)) == r['report_digest'])
    require(report.get('run_id') == r['run_id'] and report.get('mode') == 'get_only_reconcile'
            and report.get('phase') == 'READ_ONLY_COMPLETE' and report.get('stage') == 'complete'
            and report.get('create_enabled') is False and report.get('owner') == c['owner']
            and report.get('data_sha') == c['data_sha'] and report.get('data_path') == c['data_path']
            and report.get('payload_sha256') == sha(canonical(payload(manifest['payload']))))
    observed = report.get('reconciliation')
    require(type(observed) is dict and observed.get('observed_profile_ids') == []
            and observed.get('checked') == [] and observed.get('completeness') == 'UNPROVED'
            and observed.get('parenthood') == 'UNPROVED')
    # Select only after every pin and observation check. Legacy refs are never changed.
    store.marker = 'pilot-parent-consumed-v2-' + sha(canonical({
        'owner': c['owner'], 'attempt_id': r['attempt_id']}))


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


def vendor_payload(approved):
    """Internal en is an intent label; Geni documents English as en-US."""
    approved = payload(approved)
    return dict(approved, names={'he': dict(approved['names']['he']),
                                 'en-US': dict(approved['names']['en'])})


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
    wire = vendor_payload(approved)
    report = {'schema': 1, 'mode': 'one_time_parent_pilot', 'data_sha': config['data_sha'],
              'data_path': config['data_path'], 'owner': config['owner'],
              'wire_payload_sha256': sha(canonical(wire)),
              'payload_sha256': sha(canonical(approved)), 'retry_allowed': False}
    if 'recovery' in config:
        r = config['recovery']
        report['recovery'] = {k: r[k] for k in (
            'attempt_id', 'run_id', 'report_digest', 'ciphertext_digest', 'accept_uncertainty')}
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
        response = client.request('POST', '/api/' + config['owner'] + '/add-parent', wire)
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
        report['readback'] = verify(client, config, created_id, wire)
        report['phase'] = 'VERIFIED'
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
                http.client.HTTPException, subprocess.SubprocessError) as exc:
        report['stopped_stage'] = progress.stage
        report['failure_code'] = exc.code if isinstance(exc, TransportStop) else 'validation_or_storage'
        if isinstance(exc, TransportStop) and exc.evidence:
            report['http_failure'] = exc.evidence
        report['follow_up'] = 'GET-only reconciliation or separately approved repair; never retry create'
    progress.enter('final')
    store.receipt('final', save(report))
    if 'stopped_stage' in report:
        progress.enter(report['stopped_stage'])
    return report['phase']


def run(env, progress=None):
    progress = progress or Progress()
    if env.get('PILOT_DEBUG') == '1':
        progress.enable_debug()
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
    github = HTTPS('api.github.com', env.get('FAMILY_TREE_PAT', ''), github=True,
                   capture_failure=True)
    store = PrivateGit(github, config['data_repo'], config['data_sha'], config['owner'])
    progress.enter('private_source')
    manifest = store.load(config['data_path'])
    if 'recovery' in config:
        progress.enter('recovery')
        admit_recovery(store, config, manifest)
    progress.enter('credential')
    client = HTTPS('www.geni.com', env.get('GENI_SECONDARY_ACCESS_TOKEN', ''),
                   capture_failure=True)
    progress.enter('output')
    output = Path(env['PILOT_OUTPUT_DIR'])
    require(output.is_absolute() and not output.exists())
    output.mkdir(mode=0o700)
    def save(report):
        report = dict(report)
        if progress.trace is not None:
            report['debug_trace'] = list(progress.trace)
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
    try:
        return execute(config, manifest, client, store, save, progress=progress)
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError, AttributeError,
            http.client.HTTPException, subprocess.SubprocessError) as exc:
        # Local only. A failed receipt must never trigger another remote write or send.
        save({'schema': 1, 'mode': 'one_time_parent_pilot', 'phase': 'STOPPED',
              'stage': progress.stage, 'retry_allowed': False,
              'failure_code': exc.code if isinstance(exc, TransportStop) else 'validation_or_storage',
              **({'http_failure': exc.evidence} if isinstance(exc, TransportStop)
                 and exc.evidence else {})})
        raise


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
