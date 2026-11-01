"""Offline exact parent proposal view. Never authorizes production creation."""
import argparse
import html
import json
import os
from pathlib import Path

from geni_uploader.core import proposal_review
from geni_uploader.core.people import Blocked, require
from geni_uploader.core.probe import protected_file
from geni_uploader.workflow.release_gate import require_production_release

BLOCKERS = proposal_review.BLOCKERS
proposal = proposal_review.proposal
verify_proposal = proposal_review.verify_proposal


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
