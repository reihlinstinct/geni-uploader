"""Offline exact parent proposal view. Never authorizes production creation."""
import argparse
import copy
import html
import json
import os
import re
from pathlib import Path

from human_parent_gate import require_production_release
from parent_probe import protected_file
from parent_runner import payloads
from people_core import Blocked, digest, exact, require, validate, warnings

BLOCKERS = ('owner_connection_identity_not_verified', 'exact_owner_create_approval_not_verified',
            'hidden_parent_completeness_unproved', 'add_parent_slot_semantics_unproved',
            'private_and_default_locale_create_readback_unproved',
            'production_human_runner_not_implemented')


def proposal(data, pins):
    """A draft, not an authenticated remote plan receipt. No live state read."""
    data = copy.deepcopy(validate(data))
    exact(pins, ('data_sha', 'workflow_sha', 'image_digest'))
    for key in ('data_sha', 'workflow_sha'):
        require(type(pins[key]) is str and re.fullmatch(r'[a-f0-9]{40}', pins[key]))
    require(type(pins['image_digest']) is str
            and re.fullmatch(r'sha256:[a-f0-9]{64}', pins['image_digest']))
    proposed = payloads(data)
    entries = []
    for parent, payload in zip(data['parents'], proposed, strict=True):
        require(parent['gender'] in ('male', 'female'))
        # A Hebrew input must retain Hebrew and English, with explicit review.
        require('he' in parent['names'] and 'en' in parent['names'])
        entries.append({'operation': parent['local_id'], 'action': 'create_parent',
                        'anchor': parent['anchor'], 'proposed_payload': payload,
                        'payload_hash': digest(payload),
                        'readiness': 'blocked', 'duplicate_status': 'not_checked'})
    basis = {'schema_version': 1, 'kind': 'offline_parent_proposal',
             'owner': data['owner'], 'operator': data['operator'],
             'approval_as_supplied_not_authenticated': data['approval'],
             'manifest_hash': digest(data), 'pins': copy.deepcopy(pins),
             'entries': entries, 'blockers': list(BLOCKERS), 'warnings': warnings(data),
             'creation_enabled': False, 'live_checks_performed': False,
             'approval_grants_write': False}
    return {**basis, 'proposal_hash': digest(basis)}


def verify_proposal(value):
    exact(value, ('schema_version', 'kind', 'owner', 'operator',
                  'approval_as_supplied_not_authenticated', 'manifest_hash', 'pins', 'entries',
                  'blockers', 'warnings', 'creation_enabled', 'live_checks_performed',
                  'approval_grants_write', 'proposal_hash'))
    expected = value['proposal_hash']
    basis = {k: v for k, v in value.items() if k != 'proposal_hash'}
    require(type(expected) is str and expected == digest(basis))
    require(value.get('creation_enabled') is False and value.get('live_checks_performed') is False
            and value.get('approval_grants_write') is False and value.get('blockers') == list(BLOCKERS))
    require(type(value.get('entries')) is list and 1 <= len(value['entries']) <= 2)
    for entry in value['entries']:
        exact(entry, ('operation', 'action', 'anchor', 'proposed_payload', 'payload_hash',
                      'readiness', 'duplicate_status'))
        require(entry['action'] == 'create_parent' and entry['readiness'] == 'blocked'
                and entry['duplicate_status'] == 'not_checked')
        require(entry['anchor'] == value['owner']['node'])
        require(entry['payload_hash'] == digest(entry['proposed_payload']))
    # Rebuild the canonical proposal, rather than trusting a self-recomputed hash.
    reconstructed = {'schema_version': 1, 'owner': value['owner'], 'operator': value['operator'],
                     'approval': value['approval_as_supplied_not_authenticated'], 'parents': []}
    for entry in value['entries']:
        payload = entry['proposed_payload']
        require(type(payload) is dict and type(payload.get('names')) is dict
                and type(payload['names'].get('en')) is dict)
        exact(payload, ('names', *payload['names']['en'],
                        'gender', 'is_alive', 'public'))
        reconstructed['parents'].append({'local_id': entry['operation'], 'relation': 'parent',
                                         'anchor': entry['anchor'], 'names': payload['names'],
                                         'gender': payload['gender'], 'is_alive': payload['is_alive'],
                                         'public': payload['public']})
    require(digest(proposal(reconstructed, value['pins'])) == digest(value))
    return expected


def render(value):
    verify_proposal(value)
    def escape(v):
        return html.escape(str(v), quote=True)
    cards = []
    for entry in value['entries']:
        payload = entry['proposed_payload']
        rows = []
        for locale in ('he', 'en'):
            fields = payload['names'][locale]
            rows.append('<dt>'+escape(locale)+'</dt><dd>'+escape(' '.join(fields.values()))+'</dd>')
        cards.append('<section><h2>הורה חדש, לא עדכון לפרופיל קיים</h2><dl>'+''.join(rows)
                     +'<dt>מגדר שסופק</dt><dd>'+escape(payload['gender'])+'</dd>'
                     +'<dt>מצב חיים שסופק</dt><dd>'+('בחיים' if payload['is_alive'] else 'נפטר/ה')+'</dd>'
                     +'<dt>פרטיות נדרשת</dt><dd>פרטי בלבד (public:false)</dd>'
                     +'<dt>יעד הקישור</dt><dd dir="ltr">'+escape(entry['anchor'])+'</dd></dl>'
                     +'<p>אין עדיין בדיקת כפילויות או הוכחת מקום פנוי לקשר.</p>'
                     +'<details><summary>כל השדות המוצעים, כולל שדות השם הראשיים באנגלית</summary><pre dir="ltr">'
                     +escape(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))+'</pre></details></section>')
    return '''<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>טיוטת תוכנית הורים פרטית</title><style>
body{margin:0;background:#f4efec;color:#292326;font:18px/1.5 sans-serif}
main{max-width:780px;margin:24px auto;padding:24px;background:#fff;border-radius:16px}
h1{font-size:28px}h2{font-size:21px}section{padding:20px;border:1px solid #ddd;border-radius:12px;margin:20px 0}
.banner{background:#fff1dd;padding:18px;border-radius:10px}dt{font-weight:bold}dd{margin:0 0 12px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}code{overflow-wrap:anywhere;word-break:break-all;display:block;direction:ltr}footer{font-size:15px;color:#625b5f}
@media(max-width:600px){main{margin:0;padding:18px;border-radius:0}h1{font-size:24px}}
</style><main><h1>טיוטת תוכנית: הוספת הורים בלבד</h1>
<div class="banner"><b>חסום ליצירה. לא בוצעו בדיקות חיות ולא נוצרו אנשים.</b>
<p>זו תצוגת נתונים מוצעים, לא אישור פעולה ולא Plan חי. אין כפתור Upload פעיל.</p></div>''' + (
        '<p>בעל העץ והיעד: '+escape(value['owner']['expect_name'])+' <span dir="ltr">'
        +escape(value['owner']['node'])+'</span></p><p>מפעיל שסופק: '+escape(value['operator'])+'</p>'
        +''.join(cards)+'<h2>מה ייכתב ומה לא</h2><p>מוצעים רק שמות בשתי השפות, מגדר, מצב חיים ופרטיות, וקשר הורה ליעד המוצג. '
        'לא מוצעים אחים, סבים, ילדים, תאריכים, מקומות לידה, כתובות, תמונות או עריכה של אדם קיים.</p>'
        '<h2>חסימות לפני הפעלה</h2><ol><li>אימות החיבור הנפרד ובעל העץ מול החשבון.</li>'
        '<li>אישור מפורש לנתונים וליצירת שני ההורים, מעבר לשבח על עיצוב התרשים.</li>'
        '<li>הוכחת הורים קיימים ומקומות לקשרים, פרטיות ושמות דו לשוניים מול ה-API.</li>'
        '<li>מסלול יצירה אנושי שנבדק, עם יומן עמיד ובדיקת תוצאה. עדיין לא נבנה.</li></ol>'
        '<p>בעתיד המפעיל יפעיל בעצמו Plan חי, יאשר את התוכנית המדויקת ואז יפעיל יצירה. '
        'שינוי נתונים, חשבון או מצב עץ יחייב תוכנית חדשה. אין ניסיון חוזר אוטומטי לאחר תוצאה לא ודאית.</p>'
        '<h2>זיהוי ההצעה</h2><code dir="ltr">'+escape(value['proposal_hash'])+'</code>'
        '<details><summary>הצעה מלאה, לרבות פינים והצהרות אישור שלא אומתו</summary><pre dir="ltr">'
        +escape(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))+'</pre></details>'
        '<footer>קובץ מקומי פרטי. אין קוד פעיל או שירות חיצוני. אין לשלוח את הקובץ לקהל שלא אושר.</footer></main></html>')


def apply(*args, **kwargs):
    require_production_release()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline private parent proposal; no network or apply')
    parser.add_argument('--manifest-file', required=True)
    parser.add_argument('--pins-file', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args(argv)
    try:
        data = json.loads(protected_file(args.manifest_file, 65536))
        pins = json.loads(protected_file(args.pins_file, 8192))
        value = proposal(data, pins)
        page = render(value)
        require(not Path(args.output_dir).exists())
        os.mkdir(args.output_dir, 0o700)
        outputs = {'proposal.json': json.dumps(value, ensure_ascii=False, indent=2), 'proposal.html': page}
        for name, content in outputs.items():
            fd = os.open(Path(args.output_dir)/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        print('parent-plan draft saved privately; live checks absent; apply disabled')
        return 0
    except (Blocked, OSError, ValueError, TypeError, RecursionError):
        print('parent-plan blocked; review protected inputs')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
