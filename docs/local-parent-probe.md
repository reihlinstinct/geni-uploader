# Local human-run parent evidence probe

For #188/#189, after the offline #193/#194 slices. This is a separate local-only
GET probe, not a create command, OAuth client or MCP tool. It is not copied into
the runtime image or workflow. No agent is permitted to run it against Geni.
Installation/release and actual provider responses still need review. The code
has only been tested with synthetic stubs, never on a real account.

The operator supplies a private connection file, an explicit protected token file
and an age PUBLIC encryption recipient. No ambient GENI_ACCESS_TOKEN fallback,
existing user's connection, remote repo or shared service is used. Input files
must be regular, owned by the current local user, mode0600 or stricter, bounded,
and not symlinks. Output goes into a new mode0700 directory as mode0600 ciphertext.
The private key stays outside the probe. No decrypted response file is written.
Use a trusted private parent directory, not a shared temporary or synced folder.
This is not protection from another process running as the same local user.

Connection schema, with invented values only:

```json
{"schema_version":1,"connection_id":"ZZseparate","owner_node":"profile-99123","expect_name":"ZZRoot ZZPerson"}
```

`owner_node` is the canonical API node, NOT an assumed website GUID. Do not guess
it. The later guided setup must establish it from the owner's account and reviewed
protected identity evidence. A GUID resolver is not part of this probe. If that
canonical ID is not yet available, stop rather than trying variants automatically.
Use the actual name fields returned by the owner's profile, not relatives' names.
Name matching alone is never identity proof: token-self, declared owner and family
focus must agree. Missing explicit merge_pending:false currently fails closed.

## Command template, not executed by maintainers

Requires reviewed checkout, Python3.11+, and a separately installed reviewed `age`
binary on the operator's machine. No package installation or account creation is
authorized by this document. Human runs:

```sh
python parent_probe.py --connection-file /PRIVATE/connection.json \
  --token-file /PRIVATE/token --recipient AGE_PUBLIC_RECIPIENT \
  --output-dir /PRIVATE/new-probe-result --confirm-read-only YES
```

Only GET routes for current profile, exact canonical owner, immediate family and
up to10 observed union IDs are callable. Hard-coded HTTPS origin, no proxies,
redirect refusal, bearer only in header, <=1MiB per response, <=20requests, 10second
minimum pacing,30second timeout, no retries. 401/429/5xx/errors stop. Nonstandard
vendor shapes stop, not guessed normalization. Returned URLs are never followed.

Encrypted payload contains minimal requested identity/name/privacy/relationship
fields, collection time and isolated connection handle. It explicitly says
creation disabled and hidden-parent/slot/create-privacy behavior unproved. It
cannot certify hidden-parent absence, writable default locale or permissions.
A later protected reviewer must bind code/data versions and consent separately;
this probe does not create an authenticated receipt or production authorization.
Failed collection prints a fixed message and may leave an empty output directory;
choose a new path for a separately authorized retry. Do not retry a429 automatically.

## Guided operator checklist, Hebrew

אין להריץ עדיין לפני השלמת ביקורת הקוד והתקנת גרסה שנבדקה. בזמן הליווי
מציגים למפעיל צעד אחד בלבד, ומחכים לתשובה לפני הצעד הבא.

1. לבחור במפורש את החשבון של בעל העץ. לא להשתמש בחשבון משפחתי אחר או
   באסימון שכבר שמור עבור אדם אחר. הפעולה הראשונה היא זיהוי החשבון בלבד.
2. בעל החשבון מבצע בעצמו את אישור האפליקציה במסלול שנבדק. אין להעביר
   סיסמה, אסימון או כתובת הפניה הכוללת סוד בצ'אט או בדואר. ההנחיות המעשיות
   למסך האישור ייקבעו לאחר אימות המסלול, ולא על ידי ניחוש כתובת.
3. לשמור את האסימון בקובץ מקומי מוגן במסלול המאושר. לא להדביק בפקודה,
   בהיסטוריית המסוף או בקובץ הנתונים. אפשר ללוות את ההגדרה בלי לראות את הסוד.
4. לוודא בנפרד את מזהה הפרופיל הקנוני ואת השם מול החשבון המיועד, וליצור
   קובץ חיבור פרטי נפרד. אם ידוע רק מספר מכתובת האתר, עוצרים לבירור.
5. לבדוק שקיימים כלי ההצפנה והמפתח הציבורי הנכונים ושהתיקייה פרטית.
   אין צורך לתת לתוכנת הבדיקה את המפתח הפרטי.
6. המפעיל מריץ בעצמו את בדיקת הקריאה בלבד. היא אינה יוצרת או משנה אנשים.
   אם הבדיקה נעצרת, לא מנסים שוב אוטומטית ולא עוברים לחשבון אחר.
7. לבדוק את התוצאה המוצפנת בערוץ הפרטי המאושר. תוצאה תקינה אינה אישור
   שהעץ ריק מהורים ואינה מאפשרת עדיין יצירה. פערי זיהוי, פרטיות או קשרים
   מחייבים עצירה ובירור.
8. לפני יצירה בעתיד: להציג את שני ההורים המדויקים עם השם בעברית ובאנגלית,
   מצב החיים והפרטיות, ולקבל אישור מפורש לנתונים ולפעולה. מסלול היצירה
   עדיין לא זמין; לא להציג למפעיל כפתור העלאה שאינו קיים.
9. רק אחרי פתרון פערי ה-API, גרסה שנבדקה ואישור התוכנית, המפעיל יפעיל
   בעצמו את היצירה המצומצמת. אין הפעלה על ידי מודל או MCP. נבדוק תוצאה
   לפי מזהים וקריאה חוזרת, לא רק הודעת הצלחה.

No concrete OAuth URL or live command with real values is a release deliverable
until the separate reviewed connection route and canonical-ID setup are ready.

### Typed evidence leaves

Private output is extracted through bounded typed leaves, not a shallow copy:
name fields are bounded text, locale maps have exact name-field keys, privacy and
life/merge flags are explicit booleans when present, and relationship arrays hold
only canonical IDs of the appropriate type with no duplicates. Nested objects,
URLs or extra name-map fields are rejected. Absent privacy remains absent, never
false. HTTP protocol failures are mapped to fixed messages without tracebacks or
provider content. These checks minimize structure leakage but cannot determine
whether a provider's otherwise valid name string contains incorrect personal data.
