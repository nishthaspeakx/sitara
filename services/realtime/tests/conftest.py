"""Fixtures shared by the call-socket suites (M9-P10b).

`media` lives here rather than in either test file because both drive the same
socket and neither owns the other's setup. The harness it builds on is
`tests/call_harness.py`.
"""

from __future__ import annotations

import pytest

from call_harness import make_media_fixture

media = pytest.fixture()(make_media_fixture)
