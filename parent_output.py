"""Review a human-supplied plaintext probe export locally. Never decrypts or calls Geni."""
import argparse
import json
import time

from parent_probe import connection, protected_file
from parent_snapshot import bounded, parse
from people_core import Blocked, exact, require

FIELDS = ('schema_version', 'connection_id', 'collected_at_unix', 'mode', 'self',
          'owner', 'family', 'unions', 'create_enabled', 'hidden_parent_completeness',
          'slot_semantics', 'privacy_create_behavior')


def review_output(value, config, now):
    """Validate supplied binding, not provenance. Caller clock is not authority.

    A recent timestamp means only a recent *claim*; signed live Plan, vendor
    proofs, current graph, consent and release all remain absent.
    """
    config = connection(config)
    bounded(value)
    exact(value, FIELDS)
    require(type(value['schema_version']) is int and value['schema_version'] == 1)
    require(value['connection_id'] == config['connection_id'])
    require(value['mode'] == 'human_read_only_probe' and value['create_enabled'] is False)
    for key in ('hidden_parent_completeness', 'slot_semantics', 'privacy_create_behavior'):
        require(value[key] == 'unproved')
    require(type(now) is int and type(value['collected_at_unix']) is int)
    require(0 <= now - value['collected_at_unix'] <= 900)
    result = parse({key: value[key] for key in ('self', 'owner', 'family', 'unions')},
                   config['owner_node'])
    return {**result, 'supplied_connection_matches': True,
            'supplied_time_within_15_minutes': True, 'source_authenticated': False, 'name_checked': False,
            'live_checks_performed_by_reviewer': False,
            'privacy_create_behavior': 'unknown', 'default_locale_behavior': 'unknown'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline supplied probe review; no live checks')
    parser.add_argument('--connection-file', required=True)
    parser.add_argument('--evidence-file', required=True)
    args = parser.parse_args(argv)
    try:
        config = json.loads(protected_file(args.connection_file, 8192))
        value = json.loads(protected_file(args.evidence_file, 1024 * 1024))
        result = review_output(value, config, int(time.time()))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Blocked, OSError, ValueError, TypeError, KeyError, RecursionError):
        print('offline human probe review blocked; inspect protected inputs')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
