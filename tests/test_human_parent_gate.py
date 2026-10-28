import json

import pytest

import human_parent_gate as g
import parent_plan
import parent_runner
from people_core import Blocked


@pytest.mark.parametrize('entry', [parent_plan.apply, parent_runner.run_production])
def test_both_production_entries_consume_shipped_closed_gate(entry, monkeypatch):
    calls = []
    original = g.CONTRACT

    class Read:
        def read_text(self, **kwargs):
            calls.append(True)
            return original.read_text(**kwargs)

    monkeypatch.setattr(g, 'CONTRACT', Read())
    with pytest.raises(Blocked, match='disabled'):
        entry({'production_create_enabled': True, 'all_proofs': True})
    assert calls == [True]


@pytest.mark.parametrize('change', ['enabled', 'proofs', 'schema', 'extra', 'invalid', 'missing'])
def test_gate_drift_or_missing_is_blocked(change, tmp_path, monkeypatch):
    value = json.loads(g.CONTRACT.read_text())
    path = tmp_path/'gate'
    if change == 'enabled': value['production_create_enabled'] = True
    if change == 'proofs': value['required_proofs'] = []
    if change == 'schema': value['schema_version'] = True
    if change == 'extra': value['ZZsecret'] = 'ZZprivate'
    if change != 'missing':
        path.write_text('ZZprivate invalid' if change == 'invalid' else json.dumps(value))
    monkeypatch.setattr(g, 'CONTRACT', path)
    with pytest.raises(Blocked) as error:
        g.require_production_release()
    assert 'ZZ' not in str(error.value)
