# Getting a Geni access token

This guide produces a Geni API access token on YOUR machine, for use with
the uploader you run yourself. The token is a password equivalent: never
paste it into chats, issues, logs, or shared documents. These steps keep it
in one local file with owner-only permissions.

Observed behavior is marked "(observed)": it is what we saw on the dates
noted, not a guarantee from Geni. Geni's own documentation is at
https://www.geni.com/platform/developer/help (requires a Geni login).

## 1. Register a Geni application

1. Log in at https://www.geni.com/ and open
   https://www.geni.com/platform/developer/apps (login required).
2. Register a new application. Note the numeric **App ID** and the **Key**
   Geni shows; keep the Key in a local file (for example `~/geni-app-key`,
   mode 600). Never commit it anywhere.
3. For the flow described here (Geni's documented "Desktop App" flow), no
   callback URL is needed. The registration form may show fields such as a
   deauthorize/callback URL - those apply to server-side integrations, not
   to this local flow.

## 2. Authorize and capture the token

1. Build the authorization URL (the uploader can print it for you):

       podman run --rm --tmpfs /work \
         -e GENI_UPLOAD_REPO=https://github.com/<you>/<repo>.git \
         -v ~/.gh-token:/run/gh-token:ro,Z \
         quay.io/reihlinstinct/geni-uploader@sha256:<pinned-digest> \
         auth-url --client-id <your-app-id>

2. Open the printed URL in your browser and authorize the application.
   (observed, 2026-10-25) The browser then lands on a Geni page that says
   "Not Found" / 404. Third-party documentation of the same flow describes
   this as expected: the token is in the page's URL, not in the page body.
3. Copy the ENTIRE URL from the browser address bar. It contains
   `access_token` and `expires_in`, with the separator characters
   percent-encoded (observed: `access_token%3D...%26expires_in%3D...`).

## 3. Save the token locally (no echo, atomic, mode 600)

Run this in a real terminal window and paste the copied URL at the hidden
prompt. If you ever see a warning that the terminal cannot hide what you
type (for example "Can not control echo"), STOP immediately - do not paste
the URL anywhere it would be visible. The script below treats that warning
as a fatal error, but the rule stands for any tool. It extracts the token, refuses anything unexpected, and writes it
atomically with owner-only permissions. It prints only the token length
and lifetime - never the token itself.

    python3 <<'PY'
    import getpass, os, re, sys, tempfile, urllib.parse, warnings

    def main():
        # If getpass cannot control terminal echo it would fall back to
        # VISIBLE input with only a warning. Promote that warning to an
        # error so the secret URL can never be echoed.
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            url = getpass.getpass("Paste the full redirect URL (hidden): ").strip()
        except (EOFError, OSError, getpass.GetPassWarning):
            sys.exit("error: hidden input unavailable - STOP; do not paste "
                     "the URL anywhere it would be visible")
        token = expires = None
        for pat in (r"access_token%3D([^%&]+)%26expires_in%3D(\d+)",
                    r"[#&?]access_token=([^&]+)&expires_in=(\d+)"):
            m = re.search(pat, url)
            if m:
                token, expires = m.group(1), int(m.group(2))
                break
        if not token:
            sys.exit("error: no access_token found - copy the ENTIRE address bar")
        # Conservative assumption (not proven): Geni tokens are alphanumeric.
        if urllib.parse.unquote(token) != token or not token.isalnum():
            sys.exit("error: unexpected encoding/characters - nothing saved")
        path = os.path.expanduser("~/.geni-token")
        if os.path.islink(path):
            sys.exit("error: refusing to write: ~/.geni-token is a symlink")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path),
                                   prefix=".geni-token.tmp.")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(token); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise
        print(f"saved token: {len(token)} chars, "
              f"expires_in={expires}s (~{expires//3600}h), file mode 600")

    main()
    PY

## 4. Lifetime, revocation, and re-authorization

- Lifetime: the `expires_in` value tells you the token's lifetime.
  (observed, 2026-10-25) A value of about 86400 seconds (24 hours) was
  issued. When a token expires or is rejected (`HTTP 401: Invalid access
  token`), repeat steps 2-3 - the old file is replaced atomically.
- Revocation: in your Geni account settings, the applications/privacy
  section lets you remove an application's access; that revokes its
  tokens. Whether re-authorizing also invalidates earlier tokens is not
  documented - do not rely on it; remove the application explicitly when
  in doubt.
- Never let the token reach a chat, an email, a git commit, or a log.
  The uploader never logs tokens, but shell history and screenshots are
  your responsibility: the steps above are designed so the token is typed
  nowhere visible.
