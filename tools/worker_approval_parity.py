"""Synthetic differential corpus only. Never authorization or network access."""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from single_human_approval_record import check, validate


def corpus():
    base = json.loads((Path(__file__).resolve().parents[1] /
                       'oauth-bootstrap/worker-approval-synthetic.json').read_text())
    cases = []

    def add(record, expected=None, now=200):
        cases.append({'raw': json.dumps(record),
                      'expectedRaw': json.dumps(record if expected is None else expected),
                      'now': now})

    add(base)
    for section in ((), ('pins',), ('sources',)):
        target = base
        for k in section:
            target = target[k]
        for key in (*target, 'ZZ_unknown'):
            for value in (None, True, False, 0, 1.5, 'ZZ', [], {}):
                r = copy.deepcopy(base)
                t = r
                for k in section:
                    t = t[k]
                t[key] = value
                add(r)
            r = copy.deepcopy(base)
            t = r
            for k in section:
                t = t[k]
            t.pop(key, None)
            add(r)
    for role in base['sources']:
        for field in (*base['sources'][role], 'ZZ_unknown'):
            for value in (None, True, 1, 'ZZ', '0' + base['sources'][role]['principal_id']):
                r = copy.deepcopy(base)
                r['sources'][role][field] = value
                add(r)
        for other in base['sources']:
            r = copy.deepcopy(base)
            r['sources'][role]['principal_id'] = r['sources'][other]['principal_id']
            add(r)
    for now in (99, 100, 499, 500, True, 1.5, 0, 2**40):
        add(base, now=now)
    for field, values in {'issued_at': (1, 2**40, True, 1.0),
                          'expires_at': (100, 101, 1000, 1001, 2**40),
                          'run_attempt': (True, 1.0, 2),
                          'run_id': ('01', '1', '9'*20, '9'*21)}.items():
        for value in values:
            r = copy.deepcopy(base)
            r['pins'][field] = value
            add(r)
    for field in base['pins']:
        e = copy.deepcopy(base)
        if type(e['pins'][field]) is int:
            e['pins'][field] += 1
        else:
            e['pins'][field] = 'ZZ'
        add(base, e)
    for value in (0, 2**40-1, 2**40, True, 1.0):
        r = copy.deepcopy(base)
        r['revocation_epoch'] = value
        add(r)
    for key, values in {'owner': ('profile-1', 'profile-'+'9'*30, 'profile-'+'9'*31, 'profile-01'),
                        'connection_id': ('Z', 'Z'*100, 'Z'*101, 'ZZ space'),
                        'nonce': ('0'*64, 'f'*64, 'a'*63, 'A'*64, 'a'*64+'\n')}.items():
        for value in values:
            r = copy.deepcopy(base)
            r['pins'][key] = value
            add(r)
    for key in ('risk_hash', 'revocation_epoch'):
        e = copy.deepcopy(base)
        e[key] = 'd'*64 if key == 'risk_hash' else 1
        add(base, e)
    for value in ([], base['exclusions'][::-1], base['exclusions'][:-1]):
        r = copy.deepcopy(base)
        r['exclusions'] = value
        add(r)
    for c in cases:
        try:
            c['validated'] = validate(json.loads(c['raw']))
        except (ValueError, TypeError, KeyError):
            c['validated'] = None
        try:
            c['checked'] = check(json.loads(c['raw']), json.loads(c['expectedRaw']), c['now'])
        except (ValueError, TypeError, KeyError):
            c['checked'] = None
    return cases


if __name__ == '__main__':
    print(json.dumps(corpus()))
