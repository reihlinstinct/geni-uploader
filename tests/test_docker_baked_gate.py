"""Behavioural tests for the baked-files drift gate's instruction matcher (#623)."""
import subprocess
from pathlib import Path

CI = Path(__file__).resolve().parents[1] / '.github/workflows/ci.yml'
PATTERN = r'^[[:space:]]*(COPY|ADD)[[:space:]]'


def _match(pattern, lines):
    p = subprocess.run(['grep', '-iE', pattern], check=False, input='\n'.join(lines),
                       capture_output=True, text=True)
    return p.stdout.splitlines()


def test_gate_pattern_pinned_in_ci():
    s = CI.read_text()
    assert "grep -iE '" + PATTERN + "' Dockerfile" in s, \
        'baked-files gate lost its case-insensitive COPY/ADD matcher'


def test_pattern_matches_case_indentation_and_add():
    hits = _match(PATTERN, ['COPY a b', 'copy a b', '  COPY a b', '\tADD a b', 'Add a b'])
    assert hits == ['COPY a b', 'copy a b', '  COPY a b', '\tADD a b', 'Add a b']


def test_pattern_rejects_non_instructions():
    assert _match(PATTERN, ['COPYX a b', '# COPY a b', 'RUN copy a b',
                            'COPYING a b', 'ONBUILD']) == []


def test_old_anchor_pattern_missed_the_reviewed_cases():
    # Regression rationale: the previous '^COPY ' matcher missed all of these.
    p = subprocess.run(['grep', '^COPY '], check=False, input='copy a b\n  COPY a b\nADD a b',
                       capture_output=True, text=True)
    assert p.stdout == ''
