"""Opt-in, masked private plan payload and offline HTML export. Never sends mail."""
import html
import json
import os
from pathlib import Path

VERDICTS = {'new', 'skip', 'blocked', 'unknown'}


def new():
    path = os.environ.get('GENI_VISUAL_PLAN')
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
    return {'version': 1, 'complete': False, 'profiles': []}


def profile(data):
    row = {'number': len(data['profiles']) + 1, 'identity': 'unconfirmed', 'sources': []}
    data['profiles'].append(row)
    return row


def source(row, kind, verdict):
    if kind not in {'documents', 'photos'} or verdict not in VERDICTS:
        raise ValueError('invalid visual verdict')
    row['sources'].append({'number': len(row['sources']) + 1,
                           'kind': kind, 'verdict': verdict})


def validate(data):
    if (type(data) is not dict or set(data) != {'version', 'complete', 'profiles'}
            or data['version'] != 1 or type(data['complete']) is not bool
            or type(data['profiles']) is not list or len(data['profiles']) > 100):
        raise ValueError('invalid visual payload')
    for i, row in enumerate(data['profiles'], 1):
        if (type(row) is not dict or set(row) != {'number', 'identity', 'sources'}
                or row['number'] != i or row['identity'] not in {'confirmed', 'unconfirmed'}
                or type(row['sources']) is not list or len(row['sources']) > 100):
            raise ValueError('invalid visual profile')
        for j, item in enumerate(row['sources'], 1):
            if (type(item) is not dict or set(item) != {'number', 'kind', 'verdict'}
                    or item['number'] != j or item['kind'] not in {'documents', 'photos'}
                    or item['verdict'] not in VERDICTS):
                raise ValueError('invalid visual source')
    return data


def save(data):
    path = os.environ.get('GENI_VISUAL_PLAN')
    if path:
        try:
            # Exclusive bounded schema: no names, IDs, paths, titles or URLs.
            payload = json.dumps(validate(data))
            with open(path, 'w', encoding='utf-8') as out:
                os.chmod(path, 0o600)
                out.write(payload)
        except (OSError, ValueError, TypeError, KeyError):
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass


def render(data, labels=None):
    """Labels are separately reviewed private data, never part of Actions output.

    A label may be shown only for an explicitly deceased profile with a cited
    classification and confirmation that every label omits living-person data.
    No API/manifest/free text is accepted by the default payload.
    """
    data = validate(data)
    labels = labels or {}
    count = sum(len(row['sources']) for row in data['profiles'])
    parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Private source plan</title>',
             ('<style>body{margin:0;background:#f4efec;color:#251f21;font:18px/1.5 sans-serif}'
             'main{margin:24px;padding:28px;background:white;border-radius:24px;max-width:680px}'
             'h1{font-size:30px;margin:0}h2{font-size:22px;margin:24px 0 8px}'
             'li{margin:12px 0}small{color:#585254}.new,.skip{color:#336e60;font-weight:600}'
             '.blocked{color:#c02030;font-weight:600}</style><main>'),
             '<h1>Private source plan</h1><p>Review only. No upload performed.</p>',
             '<p>' + ('Checks completed (not upload approval)' if data['complete'] else
                       'INCOMPLETE: do not upload') + '</p>',
             f'<p>{len(data["profiles"])} profiles / {count} proposed sources</p>']
    for row in data['profiles']:
        label = labels.get(str(row['number']), {})
        show = (label.get('life_status') == 'deceased'
                and isinstance(label.get('evidence'), str) and label['evidence'].strip()
                and label.get('reviewed_no_living_details') is True)
        name = label.get('name') if show else None
        if not isinstance(name, str) or not name.strip():
            name = f"Profile {row['number']} (living/unknown, private)"
        parts += ['<h2>' + html.escape(name[:160]) + '</h2>',
                  '<small>Identity: ' + row['identity'] + '</small><ul>']
        for item in row['sources']:
            caption = (label.get('source_labels') or {}).get(str(item['number'])) if show else None
            if not isinstance(caption, str) or not caption.strip():
                caption = f"Source {item['number']} ({item['kind']})"
            parts += ['<li>' + html.escape(caption[:240]) + ': <span class="' +
                      item['verdict'] + '">' + item['verdict'].upper() + '</span></li>']
        parts += ['</ul>']
    parts += [('<p><small>NEW: absent from listing. SKIP: already present. '
              'BLOCKED: review journal/status. UNKNOWN: checks unavailable.<br>'
              'No identities or free text shown without separate deceased-only review. '
              'Technical checks are not permission to upload. No profile creation.</small></p></main>')]
    return ''.join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload')
    parser.add_argument('--html', required=True)
    parser.add_argument('--labels', help='separately reviewed deceased-only labels JSON')
    args = parser.parse_args()
    raw = Path(args.payload).read_bytes()
    if len(raw) > 1000000:
        raise ValueError('oversize visual payload')
    try:
        labels = json.loads(Path(args.labels).read_text()) if args.labels else None
        if labels is not None and (not isinstance(labels, dict)
                                   or any(not isinstance(x, dict) for x in labels.values())):
            raise ValueError('invalid labels')
        output = render(json.loads(raw), labels)
    except (ValueError, OSError, TypeError, AttributeError, KeyError):
        parser.exit(2, 'Private visual input is invalid; review payload and labels.\n')
    Path(args.html).write_text(output, encoding='utf-8')
    os.chmod(args.html, 0o600)


if __name__ == '__main__':
    main()
