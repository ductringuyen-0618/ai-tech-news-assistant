"""
Contract tests — black-box HTTP contract verification for the AI Tech News
Assistant backend.

These tests assert ONLY the public HTTP contract documented in the project
docs (README, docs/SEARCH_API.md, docs/INGESTION_GUIDE.md, the issues under
docs/issues/ and PRDs under docs/prds/). They never reach into ``src/`` or
mock private internals — if the docs say "POST /search returns a JSON body
with a ``results`` list", the test asserts exactly that.

Use the existing ``client`` fixture from ``backend/conftest.py``.
"""
