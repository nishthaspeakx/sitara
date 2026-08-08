"""Auth orchestration (§33.2 identity model):
Firebase UID = auth identity · Mongo _id = product identity · auth_identities
maps many login methods → one user. Email/phone on users are contact REPLICAS,
never authentication truth. Linking needs step-up (§22.5, stub in M1); a
duplicate-provider link raises the §32.12 choose-flow, never a silent merge.
"""

from datetime import UTC, date, datetime
from typing import Any

from bson import ObjectId
from sitara_schemas import ErrorCode

from sitara_api.auth.firebase import FirebaseVerifier, InvalidFirebaseToken, VerifiedIdentity
from sitara_api.auth.throttle import OtpThrottle
from sitara_api.config import Settings
from sitara_api.db import MongoDb
from sitara_api.errors import ApiError

MINIMUM_AGE_YEARS = 18  # §22.4 FOUNDER DECISION — 18+ only, hard gate
LOCALES = ("en", "hi-Latn", "hi")  # §2.4 launch set


def _now() -> datetime:
    return datetime.now(UTC)


#: §22.4's gate is a birthday, and a birthday is a LOCAL-calendar fact.
#: Evaluated in UTC, someone who turned 18 this morning in Kolkata is 17 for
#: the first 5½ hours of their birthday and is refused an account (§36.4).
DEFAULT_AGE_TIMEZONE = "Asia/Kolkata"


def local_today(timezone_name: str | None) -> tuple[date, str]:
    """Today's date in the user's own timezone, and the zone actually used.

    An unknown zone falls back to the launch market's rather than to UTC:
    UTC is the one choice guaranteed to be wrong for every user we have.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = timezone_name or DEFAULT_AGE_TIMEZONE
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        name = DEFAULT_AGE_TIMEZONE
        zone = ZoneInfo(name)
    return _now().astimezone(zone).date(), name


def _age_years(dob: date, today: date) -> int:
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


class AuthService:
    def __init__(
        self,
        db: MongoDb,
        verifier: FirebaseVerifier,
        throttle: OtpThrottle,
        settings: Settings,
    ) -> None:
        self._db = db
        self._verifier = verifier
        self._throttle = throttle
        self._settings = settings

    async def _verify_or_throttle(self, id_token: str, throttle_key: str) -> VerifiedIdentity:
        if await self._throttle.is_locked(throttle_key):
            raise ApiError(ErrorCode.AUTH_OTP_THROTTLED)
        try:
            identity = self._verifier.verify(id_token)
        except InvalidFirebaseToken:
            await self._throttle.record_failure(throttle_key)
            raise ApiError(ErrorCode.AUTH_INVALID_TOKEN) from None
        if identity.provider == "apple" and not self._settings.apple_signin_enabled:
            # §26.1 decision log: Apple deferred to M+2 — config-flagged stub.
            raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.apple_unavailable")
        await self._throttle.record_success(throttle_key)
        return identity

    async def _audit_age_check(
        self, uid: str, age: int, zone_used: str, today_local: date
    ) -> None:
        """§12 audit row for the §22.4 decision.

        The timezone is the whole point: an age gate that refuses someone is a
        legal act, and the same date of birth is 17 or 18 depending on the zone
        the check ran in (§36.4). `actor` is the Firebase uid rather than a
        product id — at this moment there is no user record yet.
        """
        from sitara_api.db.documents import stamp

        await self._db.audit_logs.insert_one(
            stamp(
                {
                    "actor": f"firebase:{uid}",
                    "action": "auth.age_gate",
                    "target": f"age={age};min={MINIMUM_AGE_YEARS}",
                    "before_hash": None,
                    "after_hash": None,
                    "ip": None,
                    "ts": _now(),
                    "timezone": zone_used,
                    "local_date": today_local.isoformat(),
                }
            )
        )

    async def exchange(
        self,
        id_token: str,
        throttle_key: str,
        date_of_birth: date | None,
        locale: str | None,
        timezone_name: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """One-time §34.5 exchange. Returns (user doc, is_new_user)."""
        identity = await self._verify_or_throttle(id_token, throttle_key)

        existing = await self._db.auth_identities.find_one(
            {"provider": identity.provider, "provider_uid": identity.uid}
        )
        if existing is not None:
            user = await self._db.users.find_one({"_id": existing["user_id"]})
            if user is None:  # identity without user — must never happen
                raise ApiError(ErrorCode.SYS_INTERNAL)
            return user, False

        # §27 sign-up row: verified email/phone matching an existing account
        # → offer LINK at sign-in; never a silent second account (§32.12).
        contact_match: list[dict[str, Any]] = []
        if identity.email:
            contact_match.append({"email": identity.email})
        if identity.phone:
            contact_match.append({"phone": identity.phone})
        if contact_match and await self._db.users.find_one({"$or": contact_match}):
            raise ApiError(ErrorCode.AUTH_PROVIDER_CONFLICT, "errors.auth.link_offer")

        # New sign-up: §22.4 hard age gate, before any record exists.
        if date_of_birth is None:
            raise ApiError(ErrorCode.SYS_VALIDATION, "errors.auth.dob_required")
        # §36.4: the §22.4 gate runs against the user's LOCAL calendar date,
        # never UTC. The zone used is recorded on the audit row, because "why
        # was this account refused?" is unanswerable without it.
        today_local, zone_used = local_today(timezone_name)
        age = _age_years(date_of_birth, today_local)
        await self._audit_age_check(identity.uid, age, zone_used, today_local)
        if age < MINIMUM_AGE_YEARS:
            raise ApiError(ErrorCode.AUTH_UNDERAGE)

        now = _now()
        user_doc: dict[str, Any] = {
            "firebase_uid": identity.uid,
            "email": identity.email,
            "phone": identity.phone,  # contact replicas only (§33.2)
            "display_name": identity.display_name,
            "date_of_birth": date_of_birth.isoformat(),
            "locale": locale if locale in LOCALES else "en",
            "script_pref": None,
            "timezone": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "schema_v": 1,
        }
        result = await self._db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        await self._db.auth_identities.insert_one(
            {
                "user_id": result.inserted_id,
                "provider": identity.provider,
                "provider_uid": identity.uid,
                "verified_at": now,
                "linked_at": now,
                "created_at": now,
                "updated_at": now,
                "schema_v": 1,
            }
        )
        return user_doc, True

    async def link(
        self, user_id: ObjectId, id_token: str, throttle_key: str, step_up_token: str | None
    ) -> str:
        """§22.5 account link. Step-up interface is live; enforcement lands M+2
        (config flag) — the stub records intent without blocking."""
        if self._settings.step_up_enforced and not step_up_token:
            raise ApiError(ErrorCode.AUTH_FORBIDDEN, "errors.auth.step_up_required")

        identity = await self._verify_or_throttle(id_token, throttle_key)

        existing = await self._db.auth_identities.find_one(
            {"provider": identity.provider, "provider_uid": identity.uid}
        )
        if existing is not None:
            if existing["user_id"] == user_id:
                return identity.provider  # idempotent re-link
            await self._open_conflict(user_id, existing["user_id"], identity.provider)
            raise ApiError(ErrorCode.AUTH_PROVIDER_CONFLICT)

        now = _now()
        await self._db.auth_identities.insert_one(
            {
                "user_id": user_id,
                "provider": identity.provider,
                "provider_uid": identity.uid,
                "verified_at": now,
                "linked_at": now,
                "created_at": now,
                "updated_at": now,
                "schema_v": 1,
            }
        )
        return identity.provider

    async def _open_conflict(
        self, current_user_id: ObjectId, other_user_id: ObjectId, provider: str
    ) -> None:
        now = _now()
        await self._db.link_conflicts.update_one(
            {"user_id": current_user_id, "status": "pending"},
            {
                "$set": {
                    "other_user_id": other_user_id,
                    "provider": provider,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "schema_v": 1},
            },
            upsert=True,
        )

    async def pending_conflict(self, user_id: ObjectId) -> dict[str, Any]:
        """§32.12 choose-flow contract: explicit user choice, side-by-side data,
        losing record archived (never merged), no automatic winner — ever."""
        conflict = await self._db.link_conflicts.find_one(
            {"user_id": user_id, "status": "pending"}
        )
        if conflict is None:
            raise ApiError(ErrorCode.SYS_VALIDATION, "errors.auth.no_pending_conflict")

        async def summary(uid: ObjectId) -> dict[str, Any]:
            user = await self._db.users.find_one({"_id": uid})
            providers = [
                doc["provider"]
                async for doc in self._db.auth_identities.find({"user_id": uid})
            ]
            return {
                "user_id": str(uid),
                "providers": providers,
                "created_at": user["created_at"].isoformat() if user else None,
                # Side-by-side birth data joins when the birth-details module
                # lands; the §32.12 contract field is present from day 1.
                "birth_details": None,
            }

        return {
            "conflict_id": str(conflict["_id"]),
            "provider": conflict["provider"],
            "prompt_key": "auth.link.conflict_prompt",
            "options": [
                {"choice": "keep_current", "account": await summary(conflict["user_id"])},
                {"choice": "keep_other", "account": await summary(conflict["other_user_id"])},
            ],
            "losing_record": "archived",
            "automatic_winner": False,
        }
