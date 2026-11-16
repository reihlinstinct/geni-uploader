"""Non-vacuous synthetic entry controls. No credentials or network. Refs #786."""
import importlib

import pytest

from geni_uploader.core.people import Blocked
from tests import test_bounded_tree_snapshot as tree
from tests import test_geni_protected_household as household
from tests import test_geni_union_child as child
from tests import test_household_precreate_read as precreate
from tests import test_household_relationship_read as relationship
from tests import test_name_update_child as mixed
from tests import test_one_time_parent_pilot as pilot
from tests import test_parent_household_read as parent_read
from tests import test_parent_pair_batch_create as batch
from tests import test_profile_name_update as name
from tests import test_profile_tgp as tgp
from tests import test_protected_parent_addition as parent
from tests import test_secondary_probe_action as secondary


class ReachedEncryption(Exception):
    """Distinct from Blocked: proves all preceding gates passed."""


def read_env(module, prefix, confirm, tmp_path):
    raw = module.h.canonical(module.cfg()) if hasattr(module, 'h') else tree.s.canonical(tree.cfg())
    core = module.h if hasattr(module, 'h') else tree.s
    return {prefix + '_CONFIRM': confirm, 'GITHUB_RUN_ATTEMPT': '1',
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': 'reihlinstinct/geni-uploader',
            'GITHUB_REF': 'refs/heads/master', 'GITHUB_ACTOR': 'reihlinstinct',
            'GITHUB_TRIGGERING_ACTOR': 'reihlinstinct',
            prefix + '_CONFIG_JSON': raw.decode(), prefix + '_CONFIG_SHA256': core.sha(raw),
            prefix + '_EXECUTOR_SHA': 'a' * 40, 'GITHUB_SHA': 'a' * 40,
            'GITHUB_RUN_ID': '990001', prefix + '_OUTPUT_DIR': str(tmp_path / 'ZZ-output')}


def build(case, tmp_path):
    namespace = 'geni_uploader.runners.'
    if case == 'pilot':
        return pilot.p, pilot.pilot_environment(tmp_path), 'PILOT_CONFIRM'
    if case == 'parent':
        return parent.p, parent.env(parent.plan(), tmp_path), 'PARENT_CONFIRM'
    if case in ('child', 'household', 'mixed'):
        data = {'child': child, 'household': household, 'mixed': mixed}[case]
        env = household.env(dict(data.plan(), target_union=household.UNION), tmp_path)
        prefix, confirm = {
            'child': ('UNION_CHILD', 'CREATE_ONE_UNION_CHILD'),
            'household': ('HOUSEHOLD_CREATE', 'CREATE_APPROVED_HOUSEHOLD'),
            'mixed': ('MIXED_CHILD', 'UPDATE_NAME_THEN_CREATE_CHILD')}[case]
        env = {k.replace('HOUSEHOLD_CREATE', prefix): v for k, v in env.items()}
        env[prefix + '_CONFIRM'] = confirm
        return data.p, env, prefix + '_CONFIRM'
    if case.startswith('tgp-'):
        mode = case.split('-')[1]
        env = {k.replace('RELATIVE_', 'TGP_'): v
               for k, v in name.environment(tgp.plan('title'), tmp_path, mode).items()}
        env['TGP_CONFIRM'] = 'READ_ONLY_TGP' if mode == 'plan' else 'UPDATE_APPROVED_TGP'
        return tgp.runner, env, 'TGP_CONFIRM'
    if case == 'batch':
        return batch.r, batch.env(tmp_path)[0], 'PAIR_CONFIRM'
    if case == 'secondary':
        return secondary.p, secondary.env(tmp_path), 'PROBE_CONFIRM'
    module, path, prefix, confirm = {
        'relationship': (relationship, 'household_relationship_read', 'HOUSEHOLD',
                         'READ_ONLY_HOUSEHOLD_RECONCILE'),
        'precreate': (precreate, 'household_precreate_read', 'HOUSEHOLD',
                      'READ_ONLY_HOUSEHOLD_BASELINE'),
        'tree': (tree, 'bounded_tree_snapshot', 'SNAPSHOT', 'READ_ONLY_BOUNDED_TREE'),
        'parent-read': (parent_read, 'parent_household_read', 'HOUSEHOLD',
                        'READ_ONLY_PARENT_HOUSEHOLDS')}[case]
    return importlib.import_module(namespace + path), read_env(module, prefix, confirm, tmp_path), prefix + '_CONFIRM'


CASES = ['pilot', 'parent', 'child', 'household', 'mixed', 'tgp-plan', 'tgp-update',
         'batch', 'relationship', 'precreate', 'tree', 'parent-read', 'secondary']


def boundary(module, monkeypatch):
    if hasattr(module, 'time'):
        monkeypatch.setattr(module.time, 'time', lambda: 200)
    def reached(*_args):
        raise ReachedEncryption()
    monkeypatch.setattr(module, 'encrypt', reached)
    for key in ('HTTPS', 'Vendor', 'ScopedVendor', 'ReadOnly'):
        if hasattr(module, key):
            monkeypatch.setattr(module, key,
                                lambda *_a, **_k: pytest.fail('ZZ network boundary'))


@pytest.mark.parametrize('case', CASES)
def test_valid_confirmation_reaches_distinct_encryption_boundary(case, tmp_path, monkeypatch):
    module, env, _key = build(case, tmp_path)
    boundary(module, monkeypatch)
    with pytest.raises(ReachedEncryption):
        module.run(env)


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('bad', [None, '', 'ZZ_WRONG_CONFIRM'])
def test_confirmation_rejected_before_encryption(case, bad, tmp_path, monkeypatch):
    module, env, key = build(case, tmp_path)
    boundary(module, monkeypatch)
    if bad is None:
        del env[key]
    else:
        env[key] = bad
    with pytest.raises(Blocked):
        module.run(env)


OTHER_TGP = {'tgp-plan': 'UPDATE_APPROVED_TGP', 'tgp-update': 'READ_ONLY_TGP'}


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('variant', ['lower', 'lead-space', 'trail-newline', 'other-mode'])
def test_near_miss_confirmation_rejected(case, variant, tmp_path, monkeypatch):
    module, env, key = build(case, tmp_path)
    boundary(module, monkeypatch)
    good = env[key]
    if variant == 'other-mode':
        if case not in OTHER_TGP:
            pytest.skip('single-mode entry point')
        env[key] = OTHER_TGP[case]
    else:
        env[key] = {'lower': good.lower(), 'lead-space': ' ' + good,
                    'trail-newline': good + '\n'}[variant]
    with pytest.raises(Blocked):
        module.run(env)
