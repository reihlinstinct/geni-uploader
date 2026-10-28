"""Human-run OAuth refresh. No profile APIs, CLI values, token output or retries."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = 'https://www.geni.com/platform/oauth/request_token'
BUNDLE_SECRET = 'GENI_OAUTH_REFRESH_BUNDLE'
ACCESS_SECRET = 'GENI_ACCESS_TOKEN'


class RenewalError(Exception):
    """Fixed public diagnostic only."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RenewalError('redirect_refused')


def credential(value):
    if not isinstance(value, str) or not value or len(value) > 16384:
        raise RenewalError('invalid_credential')
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise RenewalError('invalid_credential')
    return value


def load_bundle(raw):
    try:
        b = json.loads(raw)
        if not isinstance(b, dict) or b.get('schema') != 1:
            raise RenewalError('invalid_bundle')
        for key in ('client_id', 'client_secret', 'refresh_token'):
            credential(b[key])
        url = urllib.parse.urlsplit(b['redirect_uri'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.fragment or url.query or url.port not in (None, 443)):
            raise RenewalError('invalid_redirect_uri')
        if len(b['redirect_uri']) > 2048:
            raise RenewalError('invalid_redirect_uri')
        return {k: b[k] for k in ('schema', 'client_id', 'client_secret',
                                 'refresh_token', 'redirect_uri')}
    except (ValueError, KeyError, TypeError):
        raise RenewalError('invalid_bundle') from None


def refresh(bundle, transport=None):
    """POST form only. Never put credentials in a URL. Response must rotate safely."""
    body = urllib.parse.urlencode({
        'client_id': bundle['client_id'], 'client_secret': bundle['client_secret'],
        'redirect_uri': bundle['redirect_uri'], 'refresh_token': bundle['refresh_token'],
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method='POST', headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json',
    })
    open_request = transport or urllib.request.build_opener(NoRedirect()).open
    try:
        with open_request(req, timeout=30) as response:
            if response.status != 200 or response.geturl() != ENDPOINT:
                raise RenewalError('oauth_response_rejected')
            raw = response.read(65537)
        if len(raw) > 65536:
            raise RenewalError('oauth_response_rejected')
        d = json.loads(raw)
        if not isinstance(d, dict) or 'error' in d:
            raise RenewalError('oauth_response_rejected')
        token = credential(d['access_token'])
        rotated = credential(d['refresh_token'])
        expiry = d['expires_in']
        if type(expiry) is not int or expiry <= 0:
            raise RenewalError('oauth_response_rejected')
        return token, rotated, expiry
    except RenewalError:
        raise
    except Exception:  # noqa: BLE001 - suppress all credential-bearing transport errors
        raise RenewalError('oauth_request_failed') from None


def gh(args, value=None):
    """Never inherit raw output/errors in the workflow log."""
    result = subprocess.run(['gh', *args], input=value, text=True,
                            capture_output=True,
                            timeout=40, check=False)
    if result.returncode:
        raise RenewalError('github_operation_failed')
    return result.stdout


def run(raw, repo, call=gh, transport=None, clock=time.time):
    # Fixed destination from workflow context, never from Geni response or dispatch input.
    if repo != 'reihlinstinct/geni-uploader':
        raise RenewalError('repository_refused')
    bundle = load_bundle(raw)
    call(['api', f'repos/{repo}/actions/secrets/public-key'])
    # A prior rotation may have saved a new bundle but failed the compatibility
    # secret update. Recover that access token BEFORE using another refresh token.
    original = json.loads(raw)
    pending_expiry = original.get('pending_expires_at')
    pending_fresh = (type(pending_expiry) is int and pending_expiry > int(clock()) + 60)
    if 'pending_access_token' in original and pending_fresh:
        pending = credential(original['pending_access_token'])
        call(['secret', 'set', ACCESS_SECRET, '--repo', repo], pending)
        call(['secret', 'set', BUNDLE_SECRET, '--repo', repo], json.dumps(bundle))
        return 'recovered_previous_rotation'
    token, rotated, expiry = refresh(bundle, transport)
    bundle['refresh_token'] = rotated
    bundle['pending_access_token'] = token
    bundle['expires_in'] = expiry
    bundle['pending_expires_at'] = int(clock()) + expiry
    # Persist the rotated credential first, as one encrypted JSON secret.
    # Never silently continue after any failure and never retry refresh blindly.
    try:
        call(['secret', 'set', BUNDLE_SECRET, '--repo', repo], json.dumps(bundle))
    except Exception:  # noqa: BLE001 - never expose secret writer errors
        raise RenewalError('rotation_persist_failed_reconsent_may_be_needed') from None
    call(['secret', 'set', ACCESS_SECRET, '--repo', repo], token)
    bundle.pop('pending_access_token')
    bundle.pop('pending_expires_at')
    call(['secret', 'set', BUNDLE_SECRET, '--repo', repo], json.dumps(bundle))
    return 'renewal_saved'


def main():
    try:
        result = run(os.environ.pop('OAUTH_BUNDLE', ''),
                     os.environ.get('GITHUB_REPOSITORY', ''))
        print(result)
        return 0
    except Exception as error:  # noqa: BLE001 - fixed public output boundary
        code = str(error) if isinstance(error, RenewalError) else 'renewal_failed'
        print('STOP: ' + code)
        return 1


if __name__ == '__main__':
    sys.exit(main())
