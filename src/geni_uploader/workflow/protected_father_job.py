"""Unreleased protected-job collector. Fixed GitHub GETs; no dispatch or Geni POST.

A future protected environment job may call collect_from_environment. This module
is not installed in a workflow. Configuration/credential provenance and exact
independent review capture remain release obligations, not claims from hashes.
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from geni_uploader.core.people import Blocked, digest, exact, require
from geni_uploader.evidence.github_review import inspect, requests
from geni_uploader.evidence.single_human_approval import validate


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: require(False))


def plan_fingerprint(record):
    """Pre-dispatch exact static plan binding; not an approval record digest.

    Existing parent_envelope.envelope_hash describes the older all-proofs path,
    not this one-father v2 risk ceremony. Keep that contract unchanged. Exclude
    only run/time and human action capture, which do not exist before dispatch.
    Agent review/dispatch sources and expected human identity remain bound.
    """
    r = validate(record)
    static = {k: v for k, v in r.items() if k not in ('pins', 'sources')}
    static['pins'] = {k: v for k, v in r['pins'].items()
                      if k not in ('run_id', 'run_attempt', 'issued_at', 'expires_at')}
    static['expected_human_id'] = r['sources']['owner_grant']['principal_id']
    static['agent_sources'] = {role: r['sources'][role] for role in ('dispatch', 'code_review')}
    static['run_attempt'] = 1
    static['max_window_seconds'] = 900
    return digest(static)


def collect_from_environment(output):
    """Fixed environment inputs only. No request-controlled repository or record.

    Creates one exclusive local file, never uploads or changes a GitHub ref.
    Exceptions leave any created receipt in place; there is no automatic retry.
    The output is confidential evidence, not permission for a vendor request.
    """
    try:
        raw = os.environ['FATHER_JOB_RELEASE_JSON'].encode()
        require(0 < len(raw) <= 65536)
        require(hashlib.sha256(raw).hexdigest() == os.environ['FATHER_JOB_RELEASE_SHA256'])
        config = _decode(raw)
        require(json.dumps(config, separators=(',', ':'), ensure_ascii=False).encode() == raw)
        exact(config, ('mode', 'production_enabled', 'review_pins', 'record', 'job_name', 'plan_fingerprint'))
        require(config['mode'] == 'unreleased_protected_job_capture'
                and config['production_enabled'] is False)
        pins, record = config['review_pins'], validate(config['record'])
        require(pins['attempt'] == 1 and pins['branch'] == 'master'
                and pins['environment'] == 'father-create')
        require(str(pins['run_id']) == os.environ['GITHUB_RUN_ID']
                and os.environ['GITHUB_RUN_ATTEMPT'] == '1'
                and pins['sha'] == os.environ['GITHUB_SHA']
                and os.environ['GITHUB_REF'] == 'refs/heads/master'
                and os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
                and f"{pins['owner']}/{pins['repo']}" == os.environ['GITHUB_REPOSITORY']
                and str(pins['actor_id']) == os.environ['GITHUB_ACTOR_ID'])
        require(record['pins']['run_id'] == str(pins['run_id'])
                and record['pins']['executor_sha'] == pins['sha']
                and record['pins']['workflow_sha'] == pins['sha'])
        require(record['sources']['owner_grant']['principal_id'] == str(pins['reviewer_id'])
                and record['sources']['dispatch']['principal_id'] == str(pins['actor_id']))
        # The proposed gate names only the immutable plan and risk hashes, no names.
        require(config['plan_fingerprint'] == plan_fingerprint(record))
        expected_job = (f"Approve plan {config['plan_fingerprint']} risk {record['risk_hash']} "
                        f"run {pins['run_id']} attempt 1")
        require(config['job_name'] == expected_job)
        token = os.environ['FATHER_JOB_READ_TOKEN']
        require(0 < len(token) <= 4096 and token.isascii()
                and all(c.isalnum() or c == '_' for c in token))
        opener = urllib.request.build_opener(_NoRedirect())
        started = time.monotonic()

        def get(descriptor):
            require(time.monotonic() - started < 15)
            req = urllib.request.Request('https://api.github.com' + descriptor['route'],
                headers={'Accept': 'application/vnd.github+json',
                         'Authorization': 'Bearer ' + token,
                         'X-GitHub-Api-Version': '2022-11-28'}, method='GET')
            with opener.open(req, timeout=min(5, max(.1, 15-(time.monotonic()-started)))) as response:
                require(response.status == 200 and response.geturl() == req.full_url
                        and response.headers.get('Link') is None)
                length = response.headers.get('Content-Length')
                require(length is None or (length.isdecimal() and int(length) <= 1048576))
                data = response.read(1048577)
                require(0 < len(data) <= 1048576 and time.monotonic()-started < 15)
                _decode(data)
                return {'request': descriptor, 'status': 200, 'redirected': False,
                        'link': None, 'raw': data}

        descriptors = requests(pins)
        snapshots = [get(descriptor) for descriptor in descriptors]
        inspect(pins, snapshots)
        # One job total, not merely one match among arbitrary extra gated jobs.
        job_route = descriptors[0]['route'] + '/attempts/1/jobs?per_page=100'
        jobs = _decode(get({'method': 'GET', 'origin': 'https://api.github.com',
            'route': job_route, 'redirects_allowed': False, 'retries_allowed': False})['raw'])
        require(type(jobs['total_count']) is int and jobs['total_count'] == 1
                and type(jobs['jobs']) is list and len(jobs['jobs']) == 1)
        job = jobs['jobs'][0]
        require(job['name'] == expected_job and job['run_id'] == pins['run_id']
                and job['run_attempt'] == 1 and job['head_sha'] == pins['sha']
                and job['status'] == 'in_progress' and job['conclusion'] is None)
        # Recheck protection after capture. Historical TOCTOU remains an accepted
        # limit, not something these repeated current snapshots can prove away.
        fresh = [snapshots[0], get(descriptors[1]), snapshots[2], get(descriptors[3])]
        inspect(pins, fresh)
        now = int(time.time())
        require(record['pins']['issued_at'] <= now < record['pins']['expires_at'])
        require(type(job['id']) is int and 0 < job['id'] < 2**63)
        capture = {'run_id': pins['run_id'], 'job_id': job['id'],
                   'proposal_hash': config['plan_fingerprint'],
                   'fresh_protections': [hashlib.sha256(fresh[i]['raw']).hexdigest() for i in (1, 3)],
                   'responses': [hashlib.sha256(s['raw']).hexdigest() for s in snapshots],
                   'config_sha256': hashlib.sha256(raw).hexdigest()}
        # Stable decision binding can be recomputed by the service from fresh
        # API reads. Raw envelope hashes stay diagnostic, not correlation keys.
        decision = {'repository_id': str(pins['repository_id']),
                    'run_id': str(pins['run_id']), 'run_attempt': 1,
                    'job_id': str(job['id']), 'environment_id': str(pins['environment_id']),
                    'reviewer_id': str(pins['reviewer_id']),
                    'actor_id': str(pins['actor_id']), 'executor_sha': pins['sha'],
                    'workflow_path': pins['workflow'],
                    'plan_fingerprint': config['plan_fingerprint'],
                    'risk_hash': record['risk_hash'],
                    'review_content_hash': digest(_decode(snapshots[2]['raw']))}
        for role in ('owner_grant', 'protected_review'):
            record['sources'][role]['source_ref'] = digest(decision)
            record['sources'][role]['content_hash'] = digest(_decode(snapshots[2]['raw']))
        record = validate(record)
        target = Path(output)
        # Private bytes; exclusive creation refuses accidental replacement.
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(json.dumps(record, separators=(',', ':')).encode())
            stream.flush()
            os.fsync(stream.fileno())
        return {'phase': 'protected_job_capture_only', 'production_enabled': False,
                'post_permitted': False, 'record_hash': digest(record),
                'capture': capture, 'decision': decision, 'exact_workflow_release_verified': False,
                'independent_review_provenance_verified': False,
                'historical_settings_verified': False}
    except (Blocked, KeyError, TypeError, ValueError, UnicodeError, OSError,
            RecursionError, IndexError, urllib.error.URLError):
        raise Blocked('protected father job blocked') from None
