"""Firebase Admin adapter (§33.2/§34.5): the ONLY thing Firebase is asked for
server-side is ID-token verification. Behind an interface so the boundary is
fakeable in tests and swappable per the §6.3 adapter rule.
"""

from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

Provider = str  # "phone" | "google" | "apple" — §6.4 auth_identities enum

_SIGN_IN_PROVIDER_MAP: dict[str, Provider] = {
    "phone": "phone",
    "google.com": "google",
    "apple.com": "apple",
}


class InvalidFirebaseToken(Exception):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    provider: Provider
    phone: str | None = None
    email: str | None = None
    display_name: str | None = None


class FirebaseVerifier(Protocol):
    def verify(self, id_token: str) -> VerifiedIdentity: ...


class FirebaseAdminVerifier:
    """Real Admin-SDK verification. Lazy init so tests never touch Firebase.

    Credentials come from the explicit service-account path in Settings —
    firebase_admin only reads the GOOGLE_APPLICATION_CREDENTIALS *process*
    env var, which is not guaranteed to be exported (pydantic-settings loads
    .env into the Settings object, not into os.environ).
    """

    def __init__(
        self, project_id: str | None = None, credentials_path: str | None = None
    ) -> None:
        self._project_id = project_id
        self._credentials_path = credentials_path
        self._initialised = False

    def _ensure_app(self) -> None:
        if self._initialised:
            return
        import firebase_admin

        if not firebase_admin._apps:  # noqa: SLF001 — documented idiom
            cred = (
                firebase_admin.credentials.Certificate(self._credentials_path)
                if self._credentials_path
                else None
            )
            options = {"projectId": self._project_id} if self._project_id else None
            firebase_admin.initialize_app(credential=cred, options=options)
        self._initialised = True

    def verify(self, id_token: str) -> VerifiedIdentity:
        # Init problems are server misconfiguration (→ SYS_INTERNAL via the
        # handler), NOT an invalid client token — keep them outside the except.
        self._ensure_app()
        from firebase_admin import auth as fb_auth

        try:
            decoded = fb_auth.verify_id_token(id_token)
        except Exception as exc:
            raise InvalidFirebaseToken() from exc

        sign_in_provider = (decoded.get("firebase") or {}).get("sign_in_provider", "")
        provider = _SIGN_IN_PROVIDER_MAP.get(sign_in_provider)
        if provider is None:
            raise InvalidFirebaseToken()
        return VerifiedIdentity(
            uid=decoded["uid"],
            provider=provider,
            phone=decoded.get("phone_number"),
            email=decoded.get("email"),
            display_name=decoded.get("name"),
        )


def get_verifier(request: Request) -> FirebaseVerifier:
    """FastAPI dependency — overridden in tests with a fake."""
    return request.app.state.firebase_verifier
