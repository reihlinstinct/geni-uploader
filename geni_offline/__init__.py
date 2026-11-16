"""Offline companion for geni-uploader (design: docs/API-CLIENT-DESIGN.md, refs #93).

Empty on purpose. Everything added here must stay offline: no network, no
subprocess, and no import of geni_upload or source_details. This is enforced by
tests/test_offline_zero_network.py (AST import scan plus a child-process
audit hook).
"""
