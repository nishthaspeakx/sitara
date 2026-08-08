"""Wiring: the service boots with or without a model key, and the endpoint
speaks the §34.4 envelope when it cannot answer."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sitara_api.chat_orchestration import ChatSettings, build_pipeline
from sitara_api.chat_orchestration.pipeline import ChatPipeline
from sitara_api.chat_orchestration.router import router as chat_router
from sitara_api.errors import install_error_handlers
from tests.chat.conftest import ScriptedLLM


def test_no_model_key_means_no_pipeline_not_a_crash() -> None:
    """§8: a blank provider key behaves as "down", exactly like a blank
    DivineAPI key. The service still boots and every other module serves."""
    pipeline = build_pipeline(
        chat_settings=ChatSettings(anthropic_api_key=None),
        environment="test",
        db=None,
    )

    assert pipeline is None


def test_an_injected_client_wires_the_pipeline_without_a_key() -> None:
    pipeline = build_pipeline(
        chat_settings=ChatSettings(anthropic_api_key=None),
        environment="test",
        db=None,
        llm=ScriptedLLM(),
    )

    assert isinstance(pipeline, ChatPipeline)


def test_content_capture_is_refused_outside_dev() -> None:
    """§13: message content can structurally never appear in logs. The
    refusal at wiring time is the enforcement."""
    import pytest

    with pytest.raises(ValueError, match="§13"):
        build_pipeline(
            chat_settings=ChatSettings(anthropic_api_key=None, trace_capture_content=True),
            environment="production",
            db=None,
            llm=ScriptedLLM(),
        )


def test_the_endpoint_speaks_the_canonical_envelope_when_chat_is_down() -> None:
    """§34.4: one envelope, never a custom shape — even for "not wired yet"."""
    app = FastAPI()
    app.state.chat_pipeline = None
    install_error_handlers(app)
    app.include_router(chat_router)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/v1/chat/turn",
        json={"conversation_id": "c1", "text": "hello", "locale": "en"},
    )

    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "message_key", "trace_id", "retryable"}
    assert body["code"] == "SYS_UNAVAILABLE"
    assert body["retryable"] is True


def test_every_server_rendered_string_exists_in_every_launch_locale() -> None:
    """§2.4: no silent English fallback. These are the strings the SERVICE
    renders — the crisis line, the fallback line, the declines — so a missing
    one is not a UI gap, it is Tara having nothing to say at the worst moment."""
    from sitara_api.chat_orchestration.types import LAUNCH_LOCALES
    from sitara_api.localisation import SERVER_RENDERED_KEYS, resolve, verify_catalogs

    verify_catalogs(LAUNCH_LOCALES)  # raises if any are missing

    for locale in LAUNCH_LOCALES:
        for key in SERVER_RENDERED_KEYS:
            assert resolve(key, locale).strip()


def test_the_crisis_line_names_no_helpline_number() -> None:
    """§22.9's table does not exist yet, and §5.3 forbids inventing a fact —
    a phone number in a crisis most of all."""
    import re

    from sitara_api.chat_orchestration.types import LAUNCH_LOCALES
    from sitara_api.localisation import resolve

    for locale in LAUNCH_LOCALES:
        text = resolve("chat.safety.crisis", locale)
        assert not re.search(r"\d{3,}", text), f"{locale} crisis copy carries a number"


def test_one_corrective_regeneration_is_not_a_knob() -> None:
    """§9 fixes it at one; changing it needs §31.3 change control."""
    import pytest

    with pytest.raises(ValueError, match="§31.3"):
        ChatSettings(anthropic_api_key="k", max_corrective_regenerations=3)
