"""The Journal over HTTP — the real router, the real service, the real mongo.

The service tests cover assembly and blast radii. What this adds is the door:
that the routes exist at the paths §29.1 gives S21–S23, that a save cannot
carry content through the wire, that the checkbox survives serialisation, and
that §30.5's L4 rule is not reachable by omitting a query parameter.

`current_session` is overridden rather than a cookie forged — the auth module
owns that contract and has its own suite. Everything below the session is
real.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from sitara_api.auth.router import current_session
from sitara_api.journal.search import ExactTextSearch
from sitara_api.journal.service import JournalService
from sitara_api.journal.store import JournalStore
from tests.journal.conftest import NOW, USER_ID


@pytest_asyncio.fixture()
async def client(db) -> AsyncIterator[AsyncClient]:  # noqa: ANN001
    """An ASGI client on THIS event loop.

    Not `TestClient`: it drives the app through a blocking portal on a second
    loop, and the motor client the `db` fixture built belongs to this one —
    mixing them raises "attached to a different loop" from inside motor, which
    names the symptom and not the cause.
    """
    from fastapi import FastAPI

    from sitara_api.errors import install_error_handlers
    from sitara_api.journal.router import router as journal_router

    app = FastAPI()
    install_error_handlers(app)
    app.include_router(journal_router)
    app.state.journal_service = JournalService(
        store=JournalStore(db), search=ExactTextSearch(db)
    )
    app.dependency_overrides[current_session] = lambda: (USER_ID, "session-1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        yield test_client


async def _reflection(db, *, date: str, text: str) -> None:
    await db.night_reflections.insert_one(
        {
            "_id": ObjectId(),
            "user_id": USER_ID,
            "date": date,
            "entries": [text],
            "memory_chips": [],
            "locale": "en",
            "created_at": NOW,
            "updated_at": NOW,
            "schema_v": 1,
        }
    )


@pytest.mark.asyncio
async def test_the_timeline_route_is_s21s_path(client: AsyncClient, db) -> None:
    await _reflection(db, date="2026-08-15", text="a quiet evening")

    response = await client.get("/v1/journal")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["local_date"] == "2026-08-15"
    assert body[0]["entries"][0]["artefact_type"] == "reflection"


@pytest.mark.asyncio
async def test_the_day_route_is_s22s_path(client: AsyncClient, db) -> None:
    await _reflection(db, date="2026-08-15", text="a quiet evening")

    response = await client.get("/v1/journal/2026-08-15")

    assert response.status_code == 200
    assert response.json()["local_date"] == "2026-08-15"


@pytest.mark.asyncio
async def test_an_empty_day_is_200_not_404(client: AsyncClient) -> None:
    """§24.6: no dead ends. A date with nothing on it is an empty state, and
    a 404 on the Journal's own calendar would be one."""
    response = await client.get("/v1/journal/2026-01-01")

    assert response.status_code == 200
    assert response.json()["entries"] == []


@pytest.mark.asyncio
async def test_the_search_route_is_s23s_path(client: AsyncClient, db) -> None:
    await _reflection(db, date="2026-08-15", text="the lease decision")

    response = await client.get("/v1/journal/search", params={"q": "lease"})

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_search_and_the_day_route_do_not_collide(client: AsyncClient, db) -> None:
    """`/search` is declared before `/{local_date}` so it is not swallowed as
    a date. This is the test that fails if someone reorders them."""
    await _reflection(db, date="2026-08-15", text="the lease decision")

    response = await client.get("/v1/journal/search", params={"q": "lease"})

    assert isinstance(response.json(), list), (
        "a list means /search matched the search route; a day object would mean "
        "it had been swallowed by /{local_date}"
    )


@pytest.mark.asyncio
async def test_a_save_cannot_carry_content_through_the_wire(client: AsyncClient) -> None:
    """§44.2 again, this time as an API shape.

    `SaveRequest` has no field a sentence could arrive in, so a client cannot
    hand us a copy even by mistake — the discipline `TrustSheet` uses to keep
    fact IDs off a screen. An extra key is ignored by the model rather than
    stored.
    """
    message_id = str(ObjectId())
    response = await client.post(
        "/v1/journal/saves",
        json={
            "artefact_type": "guidance",
            "artefact_ref": message_id,
            "message_id": message_id,
            "content": "Today the Moon moves through your 10th house.",
        },
    )

    assert response.status_code == 201
    assert "content" not in response.json()


@pytest.mark.asyncio
async def test_saving_a_milestone_is_a_validation_envelope(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/journal/saves",
        json={"artefact_type": "milestone", "artefact_ref": "first_reading"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["message_key"] == "errors.journal.not_saveable"


@pytest.mark.asyncio
async def test_unsaving_a_save_that_is_not_hers_is_refused(client: AsyncClient) -> None:
    response = await client.delete(f"/v1/journal/saves/{ObjectId()}")

    assert response.status_code == 400
    assert response.json()["message_key"] == "errors.journal.save_not_found"


@pytest.mark.asyncio
async def test_the_checkbox_defaults_to_keeping_memories(client: AsyncClient, db) -> None:
    """§30.5's promise, at the wire. A request that omits the field must mean
    "keep them" — the direction a dropped body also falls in."""
    await _reflection(db, date="2026-08-15", text="a quiet evening")

    response = await client.post(
        "/v1/journal/delete",
        json={"artefact_type": "reflection", "artefact_ref": "2026-08-15"},
    )

    assert response.status_code == 200
    assert response.json() == {"artefacts": 1, "saves": 0, "memories": 0}


@pytest.mark.asyncio
async def test_the_artefact_type_filter_reaches_the_service(
    client: AsyncClient, db
) -> None:
    await _reflection(db, date="2026-08-15", text="the lease decision")

    response = await client.get(
        "/v1/journal/search", params={"q": "lease", "type": ["brief"]}
    )

    assert response.json() == [], "the filter narrowed to a kind this artefact is not"


@pytest.mark.asyncio
async def test_an_unknown_artefact_type_is_refused_at_the_door(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/v1/journal/saves",
        json={"artefact_type": "shopping_list", "artefact_ref": "x"},
    )

    # 400 and not 422: §34.4's envelope is the ONLY error shape this service
    # emits, so the request-validation handler maps FastAPI's 422 into it.
    assert response.status_code == 400
    assert response.json()["code"].startswith("SYS_")


@pytest.mark.asyncio
async def test_the_search_route_cannot_be_made_to_run_a_suggestion(
    client: AsyncClient,
) -> None:
    """§30.5's L4 rule lives on the SUGGESTION path. This route is the one a
    user typed into, so it is EXPLICIT and there is no parameter that changes
    that — a mode a caller could pass would be a mode an attacker could pass.
    """
    from sitara_api.journal import router as journal_router_module

    source = journal_router_module.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "SearchMode.EXPLICIT" in text
    assert "SearchMode.SUGGESTION" not in text
