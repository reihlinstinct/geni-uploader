"""Fixed household reconciliation evidence read. No discovery or mutation."""
import copy
import os
import re
import time
from pathlib import Path

import geni_uploader.runners.bounded_tree_snapshot as snapshot
from geni_uploader.client.probe import encrypt
from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.one_time_parent_pilot import HTTPS, TransportStop, canonical, decode, sha

HARD_GET_CEILING = 50

FIELDS = ('id,guid,url,profile_url,first_name,middle_name,last_name,maiden_name,names,'
          'gender,public,is_alive,claimed,merge_pending,merged_into,unions')


def config(value):
    require(type(value) is dict and type(value.get('schema')) is int
            and value['schema'] in (1, 2))
    multi = value['schema'] == 2
    exact(value, ('schema', 'owner', 'expect_name', 'recipient', 'expires_at', 'profiles', 'unions')
          + (('max_gets',) if multi else ()))
    base = {k: v for k, v in value.items() if k not in ('profiles', 'unions', 'max_gets')}
    base['schema'] = 1  # shared identity/expiry/encryption validation uses schema 1
    snapshot.config(dict(base, limits=copy.deepcopy(snapshot.LIMITS)))
    for key, kind in (('profiles', 'profile'), ('unions', 'union')):
        values = value[key]
        require(type(values) is list)
        require((2 <= len(values) <= 24 if key == 'profiles' else 1 <= len(values) <= 47)
                if multi else len(values) == (2 if key == 'profiles' else 1))
        for node in values:
            require(snapshot.node(node, kind) == node)
        require(len(set(values)) == len(values))
    require(value['profiles'][0] == value['owner'])
    if multi:
        require(type(value['max_gets']) is int and 1 <= value['max_gets'] <= HARD_GET_CEILING)
    planned = routes(value)
    require(len(planned) <= (value['max_gets'] if multi else 6)
            and len(planned) <= HARD_GET_CEILING
            and len({route for route, _, _ in planned}) == len(planned))
    return copy.deepcopy(value)


def routes(c):
    return [('/api/' + t + '?fields=' + FIELDS + '&only_ids=true', 'owner', t)
            for t in ('profile', c['owner'])] + [item for t in c['profiles'] for item in (
                *([('/api/' + t + '?fields=' + FIELDS + '&only_ids=true', 'candidate', t)]
                  if t != c['owner'] else []),
                ('/api/' + t + '/immediate-family?only_ids=true', 'family', t))] + [
                ('/api/' + t + '?fields=id,partners,children,status&only_ids=true', 'union', t)
                for t in c['unions']]


class Vendor(HTTPS):
    def __init__(self, token, c):
        self.c = config(c)
        super().__init__('www.geni.com', token, capture_failure=True)
        self.sequence = [route for route, _, _ in routes(self.c)]

    def admit_vendor(self, method, route):
        require(method == 'GET' and self.calls < len(self.sequence)
                and self.calls < self.c.get('max_gets', 6)
                and self.calls < HARD_GET_CEILING and route == self.sequence[self.calls]
                and time.time() < self.c['expires_at'])
        self.calls += 1  # consume before wait or transport; no retry
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.c['expires_at'])
        self.last = time.monotonic()


def safe_transport_evidence(evidence):
    """Keep only bounded numeric/boolean fields, never arbitrary error strings."""
    if type(evidence) is not dict:
        return {}
    result = {}
    for key in ('http_status', 'geni_rate_limit', 'geni_rate_remaining',
                'geni_rate_window', 'retry_after_seconds'):
        value = evidence.get(key)
        if type(value) is int and (100 <= value <= 599 if key == 'http_status'
                                  else 0 <= value <= 9999999999):
            result[key] = value
    for key in ('location_present', 'link_present', 'request_id_present'):
        if type(evidence.get(key)) is bool:
            result[key] = evidence[key]
    return result


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
            actual = client.request('GET', route)
            report['responses'].append({'kind': kind, 'target': target, 'value': actual})
            save(copy.deepcopy(report))  # preserve decoded response before all body/schema validation
            snapshot.body(actual)
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
        report.update(phase='HOUSEHOLD_BASELINE_COLLECTED', stage='complete')
    except Exception as exc:  # noqa: BLE001 - fixed output, no retry
        if type(exc) is TransportStop:
            report['failure_code'] = exc.code
            report['http_failure'] = safe_transport_evidence(exc.evidence)
        report.update(phase='STOPPED', failure='transport_schema_storage_or_expiry',
                      exception_type=type(exc).__name__ if type(exc) in (TransportStop, Blocked, OSError, ValueError,
                                      TypeError, KeyError, AttributeError) else 'other')
    save(copy.deepcopy(report))
    return report


def run(env):
    require(env.get('HOUSEHOLD_CONFIRM') == 'READ_ONLY_HOUSEHOLD_BASELINE')
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
    encrypt(c['recipient'], b'household reconciliation encryption preflight')
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
                   time.time)['phase'] == 'HOUSEHOLD_BASELINE_COLLECTED'


def main():
    try:
        ok = run(os.environ)
    except Exception:  # noqa: BLE001 - fixed output only
        ok = False
    print('household reconciliation read complete; inspect encrypted evidence and visibility limits' if ok else
          'household reconciliation read stopped; inspect encrypted evidence when available; no retry')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
