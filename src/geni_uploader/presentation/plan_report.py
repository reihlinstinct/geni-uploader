"""Value-free plan reports. No manifest values or exception strings are rendered."""
import json
import os
from pathlib import Path

COUNTS = ('sources', 'profiles', 'tags', 'descriptions')
CHECKS = ('schema', 'identity', 'listing', 'preconditions')
STATUSES = frozenset({'pass', 'fail', 'skipped', 'not_required'})


def report(mode):
    if mode not in {'plan', 'details-plan'}:
        raise ValueError('invalid report mode')
    # A new attempt must not inherit readiness from an older local report.
    path = os.environ.get('GENI_PLAN_REPORT')
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {'mode': mode, 'counts': dict.fromkeys(COUNTS, 0),
            'checks': dict.fromkeys(CHECKS, 'skipped'), 'complete': False}


def upload_counts(manifest):
    targets = manifest['targets']
    items = [item for target in targets for kind in ('documents', 'photos')
             for item in target.get(kind) or []]
    return {'sources': len(items), 'profiles': len(targets),
            'tags': sum(1 + len(item.get('also_tag') or []) for item in items),
            'descriptions': sum(bool(item.get('description_en') or item.get('description'))
                                for item in items)}


def details_counts(items):
    return {'sources': len(items),
            'profiles': len({str(t['profile_id']) for i in items for t in i['targets']}),
            'tags': sum(len(i['targets']) for i in items if not i.get('description_only')),
            'descriptions': sum(bool(i['set'].get('description_en')
                                      or i['set'].get('description')) for i in items)}


def validate(data):
    if type(data) is not dict or set(data) != {'mode', 'counts', 'checks', 'complete'}:
        raise ValueError('invalid report')
    if data['mode'] not in {'plan', 'details-plan'} or type(data['complete']) is not bool:
        raise ValueError('invalid report')
    if type(data['counts']) is not dict or set(data['counts']) != set(COUNTS):
        raise ValueError('invalid report')
    if any(type(v) is not int or not 0 <= v <= 100000 for v in data['counts'].values()):
        raise ValueError('invalid counts')
    if type(data['checks']) is not dict or set(data['checks']) != set(CHECKS):
        raise ValueError('invalid report')
    if any(type(v) is not str or v not in STATUSES for v in data['checks'].values()):
        raise ValueError('invalid checks')
    return data


def render(data):
    data = validate(data)
    safe = data['complete'] and all(v in {'pass', 'not_required'}
                                    for v in data['checks'].values())
    lines = ['## Read-only plan summary', '',
             'Mode: ' + data['mode'], '',
             '| Proposed operations | Count |', '| --- | ---: |']
    lines += [f'| {key.title()} | {data["counts"][key]} |' for key in COUNTS]
    lines += ['', '| Preflight | Status |', '| --- | --- |']
    lines += [f'| {key.title()} | {data["checks"][key]} |' for key in CHECKS]
    lines += ['', 'Safe to run: ' + ('yes' if safe else 'no'),
              ('All reported checks passed.' if safe else
               'Checks failed, were skipped, or did not finish.'),
              'A write would ' + ('upload source objects and apply source tags.'
                                  if data['mode'] == 'plan' else
                                  'update existing source metadata and requested tags.'),
              'Counts are proposed, not completed writes; existing sources may be skipped.',
              'No writes performed by this plan. Fact citations remain manual.',
              ('Readiness is technical only, not permission to write. Review privately, '
               'then explicitly confirm a fresh write run.')]
    return '\n'.join(lines) + '\n'


def save(data):
    path = os.environ.get('GENI_PLAN_REPORT')
    if path:
        try:
            Path(path).write_text(json.dumps(validate(data)), encoding='utf-8')
        except (OSError, ValueError, TypeError, KeyError):
            # Optional reporting cannot replace the underlying plan outcome.
            # No exception text or partially valid readiness report escapes.
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def main():
    import sys
    try:
        raw = Path(sys.argv[1]).read_bytes()
        if len(raw) > 4096:
            raise ValueError('oversize report')
        text = render(json.loads(raw))
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        text = ('## Read-only plan summary\n\nSafe to run: no\n'
                'No valid completed report was produced. Inspect the protected log.\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
        out.write(text)


if __name__ == '__main__':
    main()
