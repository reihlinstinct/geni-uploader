"""Synthetic-only checks for private, run-local diagnostic title labels."""
import hashlib
from unittest.mock import patch

from geni_uploader.client import upload


def test_label_is_stable_within_run_without_echoing_title():
    item = {"title": "synthetic-private-title"}
    first = upload.label(item)
    assert first == upload.label(item)
    assert first.startswith("item#") and len(first) == 21
    assert item["title"] not in first
    assert first != "item#" + hashlib.sha1(item["title"].encode()).hexdigest()[:8]
    assert first != "item#" + hashlib.sha256(item["title"].encode()).hexdigest()[:16]


def test_rotation_prevents_cross_run_dictionary_matching():
    item = {"title": "synthetic-private-title"}
    with patch.object(upload, "_LABEL_KEY", b"a" * 32):
        first = upload.label(item)
        assert first != upload.label({"title": "different-synthetic-title"})
    with patch.object(upload, "_LABEL_KEY", b"b" * 32):
        assert first != upload.label(item)


def test_key_is_random_and_not_a_title_digest():
    assert isinstance(upload._LABEL_KEY, bytes)
    assert len(upload._LABEL_KEY) == 32
