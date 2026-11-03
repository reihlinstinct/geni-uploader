"""Fixed household evidence read. No discovery or mutation."""
import copy
import os
import re
import time
from pathlib import Path

import geni_uploader.runners.bounded_tree_snapshot as snapshot
from geni_uploader.client.probe import encrypt
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.one_time_parent_pilot import HTTPS, canonical, decode, sha

FIELDS = ('id,guid,url,profile_url,first_name,middle_name,last_name,maiden_name,names,'
          'gender,public,is_alive,claimed,merge_pending,merged_into,unions')


def config(value):
    exact(value, ('schema', 'owner', 'expect_name', 'recipient', 'expires_at', 'households'))
    base = {k: v for k, v in value.items() if k != 'households'}
    snapshot.config(dict(base, limits=copy.deepcopy(snapshot.LIMITS)))
    rows = value['households']
    require(type(rows) is list and len(rows) == 3)
    all_nodes = [value['owner']]
    for row in rows:
        exact(row, ('parent', 'union', 'candidate'))
        for key, kind in (('parent', 'profile'), ('union', 'union'), ('candidate', 'profile')):
            require(snapshot.node(row[key], kind) == row[key])
            all_nodes.append(row[key])
    require(len(all_nodes) == len(set(all_nodes)))
    return copy.deepcopy(value)


def routes(c):
    return [('/api/' + t + '?fields=' + FIELDS + '&only_ids=true', 'owner', t)
            for t in ('profile', c['owner'])] + [item for row in c['households'] for item in (
                ('/api/' + row['parent'] + '/immediate-family?only_ids=true', 'family', row['parent']),
                ('/api/' + row['union'] + '?fields=id,partners,children,status&only_ids=true', 'union', row['union']),
                ('/api/' + row['candidate'] + '?fields=' + FIELDS + '&only_ids=true', 'candidate', row['candidate']))]


class Vendor(HTTPS):
    def __init__(self, token, c):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.c = config(c)
        self.sequence = [route for route, _, _ in routes(self.c)]

    def admit_vendor(self, method, route):
        require(method == 'GET' and self.calls < 11 and route == self.sequence[self.calls]
                and time.time() < self.c['expires_at'])
        self.calls += 1  # consume before wait or transport; no retry
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.c['expires_at'])
        self.last = time.monotonic()


def observe(value, client, save, clock):
    c = config(value)
    report = {'phase': 'STOPPED', 'read_only': True, 'retry_allowed': False,
              'responses': [], 'requests': [], 'unknown_union_fields': [],
              'full_children_visibility': 'UNPROVED', 'profile_mutations': False}
    try:
        for route, kind, target in routes(c):
            require(clock() < c['expires_at'])
            report['stage'] = kind
            report['requests'].append({'method': 'GET', 'route': route})
            actual = snapshot.body(client.request('GET', route))
            report['responses'].append({'kind': kind, 'target': target, 'value': actual})
            save(copy.deepcopy(report))  # preserve returned evidence before validation
            if kind == 'owner':
                snapshot.identity(actual, c)
            elif kind == 'candidate':
                require(actual.get('id') == target)
            elif kind == 'family':
                require(type(actual.get('focus')) is dict and actual['focus'].get('id') == target
                        and type(actual.get('nodes')) is dict and target in actual['nodes']
                        and 1 <= len(actual['nodes']) <= 500)
                for key, item in actual['nodes'].items():
                    require(snapshot.node(key) == key and type(item) is dict)
                    require(type(item.get('edges')) is dict and len(item['edges']) <= 500)
                    for edge, rel in item['edges'].items():
                        snapshot.node(edge)
                        require(type(rel) is dict and rel.get('rel') in ('partner', 'child'))
            elif kind == 'union':
                require(actual.get('id') == target)
                for field in ('partners', 'children'):
                    if field not in actual:
                        report['unknown_union_fields'].append({'union': target, 'field': field,
                                                               'state': 'UNKNOWN_OMITTED'})
                        continue
                    require(type(actual[field]) is list and len(actual[field]) <= 500)
                    ids = [snapshot.node(v, 'profile') for v in actual[field]]
                    require(len(ids) == len(set(ids)))
        require(clock() < c['expires_at'])
        report.update(phase='HOUSEHOLD_READ_COLLECTED', stage='complete')
    except Exception as exc:  # noqa: BLE001 - fixed output, no retry
        report.update(phase='STOPPED', failure='transport_schema_storage_or_expiry',
                      exception_type=type(exc).__name__ if type(exc) in (Blocked, OSError, ValueError,
                                      TypeError, KeyError, AttributeError) else 'other')
    save(copy.deepcopy(report))
    return report


def run(env):
    require(env.get('HOUSEHOLD_CONFIRM') == 'READ_ONLY_PARENT_HOUSEHOLDS')
    for key, expected in (('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                          ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'),
                          ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_ACTOR', 'reihlinstinct'),
                          ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct')):
        require(env.get(key) == expected)
    raw = env.get('HOUSEHOLD_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('HOUSEHOLD_CONFIG_SHA256') == sha(raw)
            and env.get('HOUSEHOLD_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', ''))
            and time.time() < c['expires_at'])
    encrypt(c['recipient'], b'parent household encryption preflight')
    out = Path(env['HOUSEHOLD_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    count = 0

    def save(value):
        nonlocal count
        report = dict(value, executor_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'],
                      config_sha256=sha(raw), recorded_at=int(time.time()))
        cipher = encrypt(c['recipient'], canonical(report))
        with os.fdopen(os.open(out / ('evidence-' + str(count).zfill(3) + '.age'),
                               os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
            f.write(cipher)
            f.flush()
            os.fsync(f.fileno())
        count += 1
    return observe(c, Vendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), c), save,
                   time.time)['phase'] == 'HOUSEHOLD_READ_COLLECTED'


def main():
    try:
        ok = run(os.environ)
    except Exception:  # noqa: BLE001 - fixed output only
        ok = False
    print('parent household read complete; inspect encrypted evidence and visibility limits' if ok else
          'parent household read stopped; inspect encrypted evidence when available; no retry')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
