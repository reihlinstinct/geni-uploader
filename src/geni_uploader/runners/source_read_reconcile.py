"""Protected bounded GET-only document evidence. Never clears a journal."""
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geni_uploader.runners.protected_source_approval as gate

WORKFLOW = '.github/workflows/source-read-reconcile.yml'
FIELDS = 'id,guid,name,display_name'
DOC_FIELDS = 'id,title,source_url,description,tags,url'
MAX_PAGES = 5
MAX_CANDIDATES = 10
MAX_CALLS = 25


def config(raw, digest, clock):
    c = json.loads(raw)
    gate.require(type(c) is dict and set(c) == {'schema', 'owner_id', 'target_guid',
        'target_id', 'expect_name', 'sources', 'recipient', 'expires_at'})
    gate.require(hashlib.sha256(gate.canonical(c)).hexdigest() == digest)
    gate.require(type(c['schema']) is int and c['schema'] == 1)
    for key in ('owner_id', 'target_id'):
        gate.require(type(c[key]) is str and re.fullmatch(r'profile-[1-9][0-9]{0,29}', c[key]))
    gate.require(type(c['target_guid']) is str and re.fullmatch(r'[1-9][0-9]{0,29}', c['target_guid']))
    gate.require(type(c['expect_name']) is str and 2 <= len(c['expect_name'].split()) <= 8)
    gate.require(type(c['recipient']) is str and re.fullmatch(r'age1[0-9a-z]{58}', c['recipient']))
    gate.require(type(c['expires_at']) is int and clock() < c['expires_at'] <= clock() + 86400)
    gate.require(type(c['sources']) is list and 1 <= len(c['sources']) <= 5)
    urls = set()
    for s in c['sources']:
        gate.require(type(s) is dict and set(s) == {'source_url', 'title', 'description_sha256'})
        gate.require(type(s['source_url']) is str and 0 < len(s['source_url']) <= 2048)
        u = urllib.parse.urlsplit(s['source_url'])
        gate.require(u.scheme == 'https' and u.hostname and not u.username and not u.password
                     and not u.fragment and not any(ord(x) < 32 for x in s['source_url']))
        gate.require(s['source_url'] not in urls); urls.add(s['source_url'])
        gate.require(type(s['title']) is str and 0 < len(s['title']) <= 512)
        gate.require(type(s['description_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', s['description_sha256']))
    return c


def envelope(env, get):
    for key, value in (('GITHUB_REPOSITORY', gate.REPO), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                       ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_ACTOR', 'reihlinstinct'),
                       ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct'), ('GITHUB_RUN_ATTEMPT', '1'),
                       ('RECONCILE_CONFIRM', 'READ_ONLY_SOURCE_RECONCILE')):
        gate.require(env.get(key) == value)
    sha = env.get('RECONCILE_EXECUTOR_SHA', '')
    gate.require(re.fullmatch(r'[a-f0-9]{40}', sha) and env.get('GITHUB_SHA') == sha)
    run = env.get('GITHUB_RUN_ID', '')
    gate.require(re.fullmatch(r'[1-9][0-9]{0,19}', run))
    r = get('actions/runs/' + run)
    gate.require(r['head_sha'] == sha and r['run_attempt'] == 1 and r['path'] == WORKFLOW
        and r['head_branch'] == 'master' and r['event'] == 'workflow_dispatch'
        and r['actor']['login'] == r['triggering_actor']['login'] == 'reihlinstinct')
    p = get('environments/father-create')
    gate.require(p['can_admins_bypass'] is False and len(p['protection_rules']) == 2
                 and {x['type'] for x in p['protection_rules']} == {'required_reviewers', 'branch_policy'})
    r = next(x for x in p['protection_rules'] if x['type'] == 'required_reviewers')
    gate.require(r['prevent_self_review'] is True and len(r['reviewers']) == 1
                 and r['reviewers'][0]['reviewer']['login'] == 'reihl')
    b = get('environments/father-create/deployment-branch-policies')
    gate.require(b['total_count'] == 1 and len(b['branch_policies']) == 1
                 and b['branch_policies'][0] == dict(b['branch_policies'][0], name='master', type='branch'))


class Reader:
    """Closed request language, one use per path, bounded paced GETs only."""
    def __init__(self, c, token, *, opener=None, clock=time.monotonic, sleep=time.sleep, wallclock=time.time):
        self.c, self.token = c, token
        self.clock, self.sleep, self.wallclock = clock, sleep, wallclock
        self.seen = set(); self.candidates = set(); self.last = None
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args):
                raise gate.Blocked()
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def request(self, method, path, body=None):
        fixed = {'/api/profile?fields=id', '/api/profile-g' + self.c['target_guid'] + '?fields=' + FIELDS}
        lists = {'/api/' + self.c['target_id'] + '/documents', '/api/user/uploaded-documents'}
        allowed = set(fixed)
        for prefix in lists:
            for page in range(1, MAX_PAGES + 1):
                allowed.add(prefix + '?page=' + str(page) + '&per_page=50')
        for oid in self.candidates:
            allowed.add('/api/' + oid + '?fields=' + DOC_FIELDS)
        gate.require(method == 'GET' and body is None and path in allowed
                     and path not in self.seen and len(self.seen) < MAX_CALLS
                     and self.wallclock() < self.c['expires_at'])
        self.seen.add(path)
        if self.last is not None:
            self.sleep(max(0, 10 - (self.clock() - self.last)))
        gate.require(self.wallclock() < self.c['expires_at'])
        self.last = self.clock()
        request = urllib.request.Request('https://www.geni.com' + path,
                                        headers={'Authorization': 'Bearer ' + self.token}, method='GET')
        with self.opener.open(request, timeout=30) as r:
            raw = r.read(2_000_001)
            gate.require(len(raw) <= 2_000_000)
            return json.loads(raw)

    def admit_document(self, oid):
        gate.require(type(oid) is str and re.fullmatch(r'document-[1-9][0-9]{0,29}', oid)
                     and len(self.candidates | {oid}) <= MAX_CANDIDATES)
        self.candidates.add(oid)


def single(value):
    gate.require(type(value) is dict and 'error' not in value)
    if 'results' in value:
        gate.require(type(value['results']) is list and len(value['results']) == 1)
        value = value['results'][0]
    gate.require(type(value) is dict and 'error' not in value)
    return value


def listing(reader, prefix, capture):
    rows = []; ids = set()
    for page in range(1, MAX_PAGES + 1):
        route = prefix + '?page=' + str(page) + '&per_page=50'
        value = reader.request('GET', route); capture(route, value)
        if page == 1 and type(value) is dict and set(value) == {'results'} and value['results'] == []:
            return []
        gate.require(type(value) is dict and 'error' not in value
                     and type(value.get('results')) is list and len(value['results']) <= 50
                     and type(value.get('page')) is int and value['page'] == page)
        for row in value['results']:
            gate.require(type(row) is dict and 'error' not in row
                         and type(row.get('id')) is str and re.fullmatch(r'document-[1-9][0-9]{0,29}', row['id'])
                         and type(row.get('title')) is str and type(row.get('source_url')) is str
                         and row['id'] not in ids)
            ids.add(row['id']); rows.append(row)
        nxt = value.get('next_page'); other = value.get('next')
        gate.require(other is None or other == nxt)
        if nxt is None or nxt == '':
            gate.require(len(value['results']) < 50)
            return rows
        gate.require(type(nxt) is str and len(value['results']) > 0)
        parsed = urllib.parse.urlsplit(urllib.parse.urljoin('https://www.geni.com' + route, nxt))
        gate.require(parsed.scheme == 'https' and parsed.netloc == 'www.geni.com'
                     and parsed.path == prefix and not parsed.fragment)
        pairs = urllib.parse.parse_qsl(parsed.query, strict_parsing=True)
        gate.require(len(pairs) == len({key for key, _ in pairs}))
        query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
        gate.require(query in ({'page': [str(page + 1)]},
                               {'page': [str(page + 1)], 'per_page': ['50']}))
    raise gate.Blocked()  # page cap never means complete or absent


def reconcile(c, reader, report):
    def capture(route, value):
        report['responses'].append({'route': route, 'response': value})
    def read(route):
        value = reader.request('GET', route); capture(route, value); return single(value)
    owner = read('/api/profile?fields=id')
    gate.require(owner.get('id') == c['owner_id'])
    target = read('/api/profile-g' + c['target_guid'] + '?fields=' + FIELDS)
    gate.require(target.get('id') == c['target_id'] and str(target.get('guid')) == c['target_guid']
                 and c['expect_name'] in (target.get('name'), target.get('display_name')))
    report['identity'] = 'pass'
    target_rows = listing(reader, '/api/' + c['target_id'] + '/documents', capture)
    report['target_listing_complete'] = True
    owner_rows = listing(reader, '/api/user/uploaded-documents', capture)
    report['account_listing_complete'] = True
    by_id = {}; urls = {x['source_url'] for x in c['sources']}
    for row in target_rows + owner_rows:
        if row['source_url'] in urls:
            by_id[row['id']] = row
    gate.require(len(by_id) <= MAX_CANDIDATES)
    objects = []
    for oid in sorted(by_id):
        reader.admit_document(oid)
        obj = read('/api/' + oid + '?fields=' + DOC_FIELDS)
        gate.require(obj.get('id') == oid and obj.get('source_url') == by_id[oid]['source_url'])
        objects.append(obj)
    for s in c['sources']:
        found = [x for x in objects if x['source_url'] == s['source_url']]
        result = {'source_url': s['source_url'], 'candidate_ids': [x['id'] for x in found],
                  'state': 'UNKNOWN', 'recreate_allowed': False}
        if len(found) == 1:
            obj = found[0]; tags = obj.get('tags'); description = obj.get('description')
            metadata = obj.get('title') == s['title'] and type(description) is str and hashlib.sha256(
                description.encode()).hexdigest() == s['description_sha256']
            valid_tags = type(tags) is list and all(type(x) is str and re.fullmatch(
                r'(?:https://www\.geni\.com/api/)?profile-[1-9][0-9]{0,29}', x) for x in tags)
            if metadata and valid_tags:
                tagged = c['target_id'] in {x.removeprefix('https://www.geni.com/api/') for x in tags}
                result.update(state='EXACT_TAGGED' if tagged else 'EXACT_UNTAGGED',
                              title_description='pass', target_tagged=tagged, observed_tags=tags)
        elif not found:
            result['state'] = 'NOT_OBSERVED_IN_COMPLETE_LISTS'
        report['sources'].append(result)
    report['title_only_collisions'] = [x['id'] for x in target_rows + owner_rows
        if x['source_url'] not in urls and x['title'] in {s['title'] for s in c['sources']}]
    report['phase'] = 'READ_ONLY_COMPLETE'
    return report


def encrypt(recipient, value, path):
    subprocess.run(['age', '-r', recipient, '-o', str(path)], input=gate.canonical(value),
                   check=True, capture_output=True, env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')})


def execute(env, get, *, clock=time.time, factory=Reader, seal=encrypt):
    envelope(env, get)
    c = config(env['RECONCILE_CONFIG_JSON'], env['RECONCILE_CONFIG_SHA256'], clock)
    temp = Path(env['RECONCILE_OUTPUT_DIR'])
    gate.require(temp.is_absolute() and not temp.exists())
    temp.mkdir(mode=0o700)
    seal(c['recipient'], {'preflight': True}, temp / 'preflight.age')
    report = {'phase': 'UNKNOWN', 'responses': [], 'sources': [], 'recreate_allowed': False,
              'journal_changes': False, 'writes': 0}
    try:
        reader = factory(c, env['GENI_ACCESS_TOKEN'])
        reconcile(c, reader, report)
        gate.require(clock() < c['expires_at'])
    except Exception:
        report['phase'] = 'UNKNOWN'
        raise
    finally:
        seal(c['recipient'], report, temp / 'source-reconcile.age')
    return True


def main():
    try:
        env = os.environ
        execute(env, lambda path: gate.github_get(env['GITHUB_TOKEN'], path))
        print('source read complete; inspect encrypted evidence; no journal changes')
        return 0
    except Exception:  # noqa: BLE001 - fixed output only
        print('source read stopped; outcome UNKNOWN; no retry or journal changes')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
