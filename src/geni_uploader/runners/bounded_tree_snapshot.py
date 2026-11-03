"""Protected bounded observations only. No vendor write or identity substitution."""
import copy
import os
import re
import time
from collections import deque
from pathlib import Path

from geni_uploader.core.people import Blocked, exact, require
from geni_uploader.runners.one_time_parent_pilot import FIELDS, HTTPS, canonical, decode, sha
from parent_probe import encrypt

LIMITS = {'hops': 3, 'profile_families': 50, 'unions': 25, 'owner_reads': 2}
NODE = r'(?:profile|union)-[1-9][0-9]{0,29}'


def node(value, kind=None):
    require(type(value) is str)
    match = re.fullmatch(r'(?:https://www\.geni\.com/api/)?(' + NODE + ')', value)
    require(match is not None)
    result = match.group(1)
    require(kind is None or result.startswith(kind + '-'))
    return result


def config(value):
    exact(value, ('schema', 'owner', 'expect_name', 'recipient', 'expires_at', 'limits'))
    require(type(value['schema']) is int and value['schema'] == 1)
    require(node(value['owner'], 'profile') == value['owner'])
    require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)
    require(type(value['recipient']) is str and re.fullmatch(r'age1[0-9a-z]{58}', value['recipient']))
    require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)
    require(type(value['limits']) is dict and value['limits'] == LIMITS
            and all(type(v) is int for v in value['limits'].values()))
    return copy.deepcopy(value)


def body(value):
    require(type(value) is dict and 'error' not in value
            and not any(k in value for k in ('next_page', 'paging', 'pagination'))
            and len(canonical(value)) <= 262144)
    return value


def identity(value, c):
    body(value)
    require(value.get('id') == c['owner'])
    tokens = ' '.join(value.get(k, '') for k in ('first_name', 'middle_name', 'last_name')).casefold().split()
    require(all(w.casefold() in tokens for w in c['expect_name'].split()))
    # Keep merge facts, including UNKNOWN, as evidence. Never redirect to another identity.


class Vendor(HTTPS):
    """Explicit one-use GET routes, fixed caps, no token refresh or retry."""
    def __init__(self, token, c):
        super().__init__('www.geni.com', token, capture_failure=True)
        self.c = config(c)
        self.allowed = set()
        self.seen = set()

    def allow(self, route):
        require(route not in self.seen)
        self.allowed.add(route)

    def admit_vendor(self, method, route):
        require(method == 'GET' and route in self.allowed and route not in self.seen
                and self.calls < 77 and time.time() < self.c['expires_at'])
        require(re.fullmatch(r'/api/(?:profile|profile-[1-9][0-9]{0,29})(?:\?fields=[A-Za-z_,]+&only_ids=true|/immediate-family\?only_ids=true)', route)
                or re.fullmatch(r'/api/union-[1-9][0-9]{0,29}\?only_ids=true', route))
        self.seen.add(route)
        if self.last is not None:
            time.sleep(max(0, 15 - (time.monotonic() - self.last)))
        require(time.time() < self.c['expires_at'])
        self.calls += 1
        self.last = time.monotonic()


def observe(value, client, save, clock):
    c = config(value)
    report = {'schema': 1, 'phase': 'STOPPED', 'stage': 'identity', 'read_only': True,
              'retry_allowed': False, 'complete_tree': False, 'limits': LIMITS,
              'responses': [], 'requests': [], 'boundary': [], 'unknown_union_fields': [], 'merge_unknown_allowed_for_read_only': True}
    queue = deque([(c['owner'], 0)])
    depths = {c['owner']: 0}
    unions = set()
    total = 0

    def read(kind, target, route):
        nonlocal total
        require(clock() < c['expires_at'])
        report['stage'] = kind
        # Record attempted request before transport. Failed requests are never retried.
        report['requests'].append({'method': 'GET', 'route': route})
        client.allow(route)
        actual = client.request('GET', route)
        body(actual)
        total += len(canonical(actual))
        require(total <= 16 * 1024 * 1024)
        report['responses'].append({'kind': kind, 'target': target, 'value': actual})
        save(copy.deepcopy(report))
        return actual

    def boundary(target, depth, reason):
        report['boundary'].append({'target': target, 'depth': depth, 'reason': reason})

    try:
        for target in ('profile', c['owner']):
            identity(read('owner', target, '/api/' + target + '?fields=' + FIELDS + '&only_ids=true'), c)
        families = 0
        while queue:
            target, depth = queue.popleft()
            if depth >= 3:
                boundary(target, depth, 'hop_limit')
                continue
            if families >= 50:
                boundary(target, depth, 'family_cap')
                continue
            families += 1
            family = read('family', target, '/api/' + target + '/immediate-family?only_ids=true')
            require(type(family.get('focus')) is dict and family['focus'].get('id') == target
                    and type(family.get('nodes')) is dict and target in family['nodes']
                    and 1 <= len(family['nodes']) <= 500)
            for key, item in sorted(family['nodes'].items()):
                current = node(key)
                require(current == key and type(item) is dict and item.get('id', key) == key)
                edges = item.get('edges')
                require(type(edges) is dict and len(edges) <= 500)
                for edge, relation in edges.items():
                    node(edge)
                    require(type(relation) is dict and relation.get('rel') in ('partner', 'child'))
                if current.startswith('profile-') and current not in depths:
                    require(len(depths) < 5000)
                    depths[current] = depth + 1
                    queue.append((current, depth + 1))
                if current.startswith('union-') and current not in unions:
                    if len(unions) >= 25:
                        boundary(current, depth, 'union_cap')
                        continue
                    unions.add(current)
                    union = read('union', current, '/api/' + current + '?only_ids=true')
                    require(union.get('id') == current)
                    for field in ('partners', 'children'):
                        if field not in union:
                            report['unknown_union_fields'].append({'union': current, 'field': field,
                                                                   'state': 'UNKNOWN_OMITTED'})
                            continue
                        require(type(union.get(field)) is list and len(union[field]) <= 500)
                        normalized = [node(v, 'profile') for v in union[field]]
                        require(len(normalized) == len(set(normalized)))
                    # Union read is corroboration only, never broadens the profile queue.
        require(clock() < c['expires_at'])
        report.update(phase='BOUNDED_SNAPSHOT_COLLECTED', stage='complete',
                      observed_profiles=len(depths), family_reads=families, union_reads=len(unions),
                      coverage='bounded_service_immediate_family_adjacency_not_whole_tree',
                      excluded='hidden nodes, pagination, outside-hop nodes and unrequested profile details')
    except Exception as exc:  # noqa: BLE001 - fixed diagnostic only; never retry
        report.update(phase='STOPPED', failure='transport_schema_storage_or_expiry',
                      exception_type=type(exc).__name__ if type(exc) in (Blocked, OSError, ValueError,
                                      TypeError, KeyError, AttributeError) else 'other')
    save(copy.deepcopy(report))
    return report


def run(env):
    require(env.get('SNAPSHOT_CONFIRM') == 'READ_ONLY_BOUNDED_TREE')
    for key, expected in (('GITHUB_RUN_ATTEMPT', '1'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                          ('GITHUB_REPOSITORY', 'reihlinstinct/geni-uploader'),
                          ('GITHUB_REF', 'refs/heads/master'), ('GITHUB_ACTOR', 'reihlinstinct'),
                          ('GITHUB_TRIGGERING_ACTOR', 'reihlinstinct')):
        require(env.get(key) == expected)
    raw = env.get('SNAPSHOT_CONFIG_JSON', '').encode()
    c = config(decode(raw))
    require(env.get('SNAPSHOT_CONFIG_SHA256') == sha(raw)
            and env.get('SNAPSHOT_EXECUTOR_SHA') == env.get('GITHUB_SHA')
            and re.fullmatch(r'[a-f0-9]{40}', env.get('GITHUB_SHA', ''))
            and time.time() < c['expires_at'])
    encrypt(c['recipient'], b'bounded tree snapshot encryption preflight')
    out = Path(env['SNAPSHOT_OUTPUT_DIR'])
    require(out.is_absolute() and not out.exists())
    out.mkdir(mode=0o700)
    count = 0

    def save(value):
        nonlocal count
        report = dict(value, executor_sha=env['GITHUB_SHA'], run_id=env['GITHUB_RUN_ID'],
                      recorded_at=int(time.time()))
        cipher = encrypt(c['recipient'], canonical(report))
        with os.fdopen(os.open(out / ('evidence-' + str(count).zfill(3) + '.age'),
                               os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
            f.write(cipher)
            f.flush()
            os.fsync(f.fileno())
        count += 1
    return observe(c, Vendor(env.get('GENI_SECONDARY_ACCESS_TOKEN', ''), c), save,
                   time.time)['phase'] == 'BOUNDED_SNAPSHOT_COLLECTED'


def main():
    try:
        ok = run(os.environ)
    except Exception:  # noqa: BLE001 - no identifying console output
        ok = False
    print('bounded tree read complete; inspect encrypted scope and boundaries' if ok else
          'bounded tree read stopped; encrypted evidence retained when available; no retry')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
