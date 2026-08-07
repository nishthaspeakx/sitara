"""§22.4 hard age gate: under-18 DOB rejected at sign-up with an honest,
in-locale explanation — AUTH_UNDERAGE, message_key resolvable in ALL launch locales.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from pymongo import MongoClient

from sitara_api.config import Settings

from .conftest import FakeVerifier, assert_envelope, exchange, years_ago

CATALOGS = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "messages"


def test_underage_dob_rejected(
    client: TestClient, verifier: FakeVerifier, mongo: MongoClient, settings: Settings
) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    resp = exchange(client, "tok-1", dob=years_ago(18, plus_days=1))  # 18 tomorrow

    assert resp.status_code == 422
    assert_envelope(resp.json(), "AUTH_UNDERAGE", retryable=False)
    assert resp.json()["message_key"] == "errors.auth.underage"
    assert "set-cookie" not in resp.headers

    # No account is created for a rejected sign-up.
    db = mongo[settings.mongo_db]
    assert db.users.count_documents({}) == 0
    assert db.auth_identities.count_documents({}) == 0


def test_exactly_eighteen_today_is_allowed(client: TestClient, verifier: FakeVerifier) -> None:
    verifier.add("tok-1", uid="fb-uid-1", provider="phone", phone="+911234500001")
    resp = exchange(client, "tok-1", dob=years_ago(18))
    assert resp.status_code == 200


def test_underage_message_key_exists_in_all_three_locales() -> None:
    """§2.4 whole-app native language — the rejection must be translatable
    everywhere, no silent English fallback."""
    for locale in ("en", "hi-Latn", "hi"):
        catalog = json.loads((CATALOGS / f"{locale}.json").read_text())
        node = catalog
        for part in "errors.auth.underage".split("."):
            assert part in node, f"{locale} catalog missing errors.auth.underage"
            node = node[part]
        assert isinstance(node, str) and node.strip()
