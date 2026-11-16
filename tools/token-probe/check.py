"""User-run token response check. Not an account-owner identity verifier."""
import json
import os
import sys
import urllib.error
import urllib.request

URL = 'https://www.geni.com/api/user'
MAX_BYTES = 65536


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def check(token, opener=None):
    # Refuse header injection, pasted URLs and accidental application keys
    # cannot be detected locally. Never print the token or an exception.
    if (not isinstance(token, str) or not 1 <= len(token) <= 8192
            or any(not 33 <= ord(c) <= 126 for c in token)
            or token.startswith(('http:', 'https:')) or 'access_token=' in token):
        return 'STOP_INVALID_TOKEN_INPUT', 1
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(
        URL, headers={'Authorization': 'Bearer ' + token,
                      'Accept': 'application/json'}, method='GET')
    try:
        # Exactly one request attempt. No redirect, retry, cookie jar or proxy.
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                return 'STOP_HTTP_RESPONSE', 1
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return 'STOP_RESPONSE_TOO_LARGE', 1
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
        if not isinstance(data, dict) or not data or 'error' in data:
            return 'STOP_UNCONFIRMED_RESPONSE', 1
        # /api/user documents name + account_type, not profile id/guid.
        # Values never leave this process; this cannot verify owner identity.
        if (not isinstance(data.get('name'), str) or not data['name'].strip()
                or data.get('account_type') not in ('basic', 'plus', 'pro')):
            return 'STOP_CONTEXT_SHAPE_UNKNOWN', 1
        return 'TOKEN_CONTEXT_RESPONSE_OK_OWNER_NOT_VERIFIED', 0
    except urllib.error.HTTPError as error:
        error.close()
        return ('STOP_RATE_LIMIT_NO_RETRY' if error.code == 429
                else 'STOP_HTTP_RESPONSE'), 1
    except Exception:  # noqa: BLE001 - fixed verdict prevents private exception disclosure
        return 'STOP_UNVERIFIABLE_RESPONSE_NO_RETRY', 1


def main():
    token = os.environ.pop('TOKEN_PROBE_CREDENTIAL', '')
    verdict, code = check(token)
    print(verdict)
    print('GENI_WRITES=0; OWNER_IDENTITY=NOT_VERIFIED')
    return code


if __name__ == '__main__':
    sys.exit(main())
