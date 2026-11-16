"""Synthetic comparison-only alias collisions; no network or text rewriting."""
import copy

import pytest

from geni_uploader.runners import bounded_alias_append as core
from tests.test_alias_append import plan


@pytest.mark.parametrize('old,new', [
    ('ZZ Re\u0301ne', 'ZZ R\u00e9ne'),
    ('ZZ\u00a0Old2', 'ZZ Old2'),
    ('ZZ  Old2', 'ZZ Old2'),
    ('ZZ Rene', 'ZZ RENE'),
    ('ZZ Stra\u00dfe', 'ZZ Strasse')])
def test_equivalent_existing_alias_blocks_before_effect(old, new):
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    before = copy.deepcopy(c)
    with pytest.raises(core.Blocked): core.plan(c)
    assert c == before


@pytest.mark.parametrize('old', ['ZZ Re\u0301ne', 'ZZ\u00a0Old2', 'ZZ  Old2'])
def test_distinct_append_preserves_stored_alias_bytes(old):
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = ['ZZ Different']
    before = copy.deepcopy(c)
    approved = core.plan(c)
    assert c == before
    assert approved['expected']['nicknames'] == [old]
    assert approved['append'] == ['ZZ Different']
    assert core.payload(approved) == {'nicknames': old + ',ZZ Different'}


@pytest.mark.parametrize('old', [
    ['ZZ Re\u0301ne', 'ZZ R\u00e9ne'],
    ['ZZ\u00a0Old2', 'ZZ Old2'],
    ['ZZ  Old2', 'ZZ Old2']])
def test_existing_only_comparison_collision_still_blocks(old):
    c = plan(); c['expected']['nicknames'] = old; c['append'] = ['ZZ Different']
    with pytest.raises(core.Blocked): core.plan(c)


# Follow-up pins from the #797 reviews (#799). Behavior pins only: no policy change.

@pytest.mark.parametrize('old,new', [('ZZ A B', 'ZZ AB'), ('ZZ AB', 'ZZ A B')])
def test_whitespace_collapse_is_not_whitespace_deletion(old, new):
    # Negative control: the key collapses runs of whitespace; it never deletes it.
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    approved = core.plan(c)
    assert approved['expected']['nicknames'] == [old]
    assert approved['append'] == [new]


@pytest.mark.parametrize('old,new', [('ZZ \ufb01n', 'ZZ fin'), ('ZZ fin', 'ZZ \ufb01n')])
def test_ligature_collides_through_casefold_without_rewrite(old, new):
    # casefold() itself maps U+FB01 to 'fi'; no NFKC is involved.
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    before = copy.deepcopy(c)
    with pytest.raises(core.Blocked): core.plan(c)
    assert c == before
    assert c['expected']['nicknames'] == [old]


def test_stored_ligature_alias_bytes_are_not_rewritten():
    c = plan(); c['expected']['nicknames'] = ['ZZ \ufb01n']; c['append'] = ['ZZ Different']
    approved = core.plan(c)
    assert approved['expected']['nicknames'] == ['ZZ \ufb01n']
    assert core.payload(approved) == {'nicknames': 'ZZ \ufb01n,ZZ Different'}


def test_case_variant_with_reordered_marks_collides():
    # Both strings are NFC. casefold() of U+01F0 emits j + U+030C ahead of U+0323,
    # which is not canonical order; only the outer NFC makes the keys equal.
    old, new = 'ZZ \u01f0\u0323a', 'ZZ J\u0323\u030ca'
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    before = copy.deepcopy(c)
    with pytest.raises(core.Blocked): core.plan(c)
    assert c == before


@pytest.mark.parametrize('old,new', [('ZZ \uff21', 'ZZ A'), ('ZZ A', 'ZZ \uff21')])
def test_compatibility_forms_stay_distinct(old, new):
    # Decided policy is NFC, not NFKC: fullwidth A (U+FF21) does not collide with A.
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    approved = core.plan(c)
    assert approved['expected']['nicknames'] == [old]
    assert approved['append'] == [new]


def test_inner_nfc_needed_for_noncanonical_stored_alias():
    # U+0345 (ccc 240) precedes U+0301 (ccc 230) in the stored value.
    # Casefold before canonical ordering would compose a different vowel.
    old, new = 'ZZ \u03b1\u0345\u0301a', 'ZZ \u1fb4a'
    c = plan(); c['expected']['nicknames'] = [old]; c['append'] = [new]
    before = copy.deepcopy(c)
    with pytest.raises(core.Blocked):
        core.plan(c)
    assert c == before
