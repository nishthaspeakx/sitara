"""Client-side field-level encryption for the fields §6.4 marks (§13).

**Explicit, not automatic.** MongoDB's automatic CSFLE (a `schemaMap` on the
client) is an Enterprise/Atlas-only feature, and the dev stack runs Community
`mongo:7`. Explicit encryption — encrypt on the way in, decrypt on the way out —
behaves identically on Community and Atlas, so dev and production run the same
code path instead of the same code path *plus a fork nobody exercises locally*.

**Two KMS providers behind one interface.** `local` reads a 96-byte master key
from a file and refuses to initialise outside dev/test (§22.12: a dev key must
never protect production data). `aws` names a CMK and lets the ambient AWS
credential chain do the rest. Which one runs is configuration, not code.

**Key classes, not one key.** §33.1 requires voice-note audio under a key class
of its own, separate from message content, so revoking one cannot silently
revoke the other. The registry names a class per encrypted field and this module
provisions one data key per class.

Deterministic encryption is used only where a field must stay equality-queryable
— the §33.2 contact replicas the nightly reconciliation looks up. Deterministic
ciphertext leaks equality (two users with the same email encrypt identically),
so everything else is randomized, which is both stronger and the default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from bson import Binary
from bson.codec_options import CodecOptions
from motor.motor_asyncio import AsyncIOMotorClientEncryption
from pymongo.encryption import Algorithm

from sitara_api.config import Settings
from sitara_api.db.connection import MongoClient
from sitara_api.db.registry import SPECS, CollectionSpec, key_classes

DETERMINISTIC = Algorithm.AEAD_AES_256_CBC_HMAC_SHA_512_Deterministic
RANDOMIZED = Algorithm.AEAD_AES_256_CBC_HMAC_SHA_512_Random

#: bson binary subtype that marks a CSFLE ciphertext.
ENCRYPTED_SUBTYPE = 6

LOCAL_MASTER_KEY_BYTES = 96
DEV_ENVIRONMENTS = frozenset({"dev", "test", "local"})


class CsfleConfigurationError(RuntimeError):
    """Raised when the encryption setup would be unsafe or is incomplete.

    Loud rather than degrading to plaintext: silently writing birth details in
    the clear because a key file was missing is the failure mode §13 exists to
    prevent.
    """


# ---------------------------------------------------------------------------
# KMS providers


class KmsProvider:
    name: str

    def credentials(self) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def master_key(self) -> dict[str, Any] | None:  # pragma: no cover - interface
        raise NotImplementedError


class LocalKmsProvider(KmsProvider):
    """Dev/test only. The master key is a file on disk, which is exactly why
    this provider refuses to run anywhere real."""

    name = "local"

    def __init__(self, key_path: Path, environment: str) -> None:
        if environment not in DEV_ENVIRONMENTS:
            raise CsfleConfigurationError(
                f"the local KMS provider is dev-only and environment is {environment!r} "
                "(§22.12) — configure CSFLE_KMS_PROVIDER=aws"
            )
        self._key = _read_or_create_master_key(key_path)

    def credentials(self) -> dict[str, Any]:
        return {"local": {"key": self._key}}

    def master_key(self) -> dict[str, Any] | None:
        return None


class AwsKmsProvider(KmsProvider):
    """Production. Credentials come from the ambient AWS chain (task role in
    ECS/EKS); §13 keeps the CMK in KMS with rotation, so nothing secret is held
    here beyond the key's ARN."""

    name = "aws"

    def __init__(self, key_arn: str, region: str) -> None:
        if not key_arn:
            raise CsfleConfigurationError("CSFLE_AWS_KMS_KEY_ARN is required for the aws provider")
        self._key_arn = key_arn
        self._region = region

    def credentials(self) -> dict[str, Any]:
        # An empty dict tells pymongo to use the ambient credential chain
        # rather than baking an access key into the process.
        return {"aws": {}}

    def master_key(self) -> dict[str, Any] | None:
        return {"provider": "aws", "region": self._region, "key": self._key_arn}


def _read_or_create_master_key(path: Path) -> bytes:
    if path.exists():
        key = path.read_bytes()
        if len(key) != LOCAL_MASTER_KEY_BYTES:
            raise CsfleConfigurationError(
                f"{path} holds {len(key)} bytes; a local master key is "
                f"{LOCAL_MASTER_KEY_BYTES}"
            )
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(LOCAL_MASTER_KEY_BYTES)
    path.write_bytes(key)
    path.chmod(0o600)
    return key


def build_provider(settings: Settings) -> KmsProvider:
    if settings.csfle_kms_provider == "local":
        path = Path(settings.csfle_local_master_key_path or ".secrets/csfle-master.key")
        return LocalKmsProvider(path, settings.environment)
    if settings.csfle_kms_provider == "aws":
        return AwsKmsProvider(settings.csfle_aws_kms_key_arn or "", settings.csfle_aws_region)
    raise CsfleConfigurationError(f"unknown KMS provider {settings.csfle_kms_provider!r}")


# ---------------------------------------------------------------------------
# The codec


class FieldCrypto:
    """Encrypts and decrypts the registry's marked fields.

    One instance per process. `provision()` is idempotent: it creates a data key
    per class the first time and finds the existing one thereafter, keyed by
    `keyAltNames`, so a redeploy never orphans data behind a fresh key.
    """

    def __init__(
        self,
        client: MongoClient,
        provider: KmsProvider,
        key_vault_namespace: str,
    ) -> None:
        self._provider = provider
        self._key_vault_namespace = key_vault_namespace
        self._client = client
        self._encryption = AsyncIOMotorClientEncryption(
            kms_providers=provider.credentials(),
            key_vault_namespace=key_vault_namespace,
            key_vault_client=client,
            codec_options=CodecOptions(),
        )
        self._keys: dict[str, Binary] = {}

    async def provision(self, classes: tuple[str, ...] | None = None) -> dict[str, Binary]:
        await self._ensure_key_vault_index()
        for name in classes or key_classes():
            self._keys[name] = await self._data_key(name)
        return dict(self._keys)

    async def _ensure_key_vault_index(self) -> None:
        db_name, coll_name = self._key_vault_namespace.split(".", 1)
        await self._client[db_name][coll_name].create_index(
            [("keyAltNames", 1)],
            unique=True,
            partialFilterExpression={"keyAltNames": {"$exists": True}},
            name="keyAltNames_1",
        )

    async def _data_key(self, key_class: str) -> Binary:
        existing = await self._encryption.get_key_by_alt_name(key_class)
        if existing is not None:
            return existing["_id"]
        return await self._encryption.create_data_key(
            self._provider.name,
            master_key=self._provider.master_key(),
            key_alt_names=[key_class],
        )

    async def close(self) -> None:
        await self._encryption.close()

    # -- per-document ------------------------------------------------------

    async def encrypt_document(
        self, spec: CollectionSpec, document: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a copy with every marked field replaced by its ciphertext.

        A field that is absent or `None` is left alone: encrypting a null would
        make "she has no middle name" indistinguishable from a value, and the
        validators accept null for the optional ones.
        """
        if not spec.encrypted:
            return document
        out = dict(document)
        for field in spec.encrypted:
            value = out.get(field.path)
            if value is None:
                continue
            if isinstance(value, Binary) and value.subtype == ENCRYPTED_SUBTYPE:
                continue  # already encrypted — re-encrypting would double-wrap
            out[field.path] = await self._encryption.encrypt(
                value,
                DETERMINISTIC if field.deterministic else RANDOMIZED,
                key_id=self._key_for(field.key_class),
            )
        return out

    async def decrypt_document(
        self, spec: CollectionSpec, document: dict[str, Any]
    ) -> dict[str, Any]:
        if not spec.encrypted:
            return document
        out = dict(document)
        for field in spec.encrypted:
            value = out.get(field.path)
            if isinstance(value, Binary) and value.subtype == ENCRYPTED_SUBTYPE:
                out[field.path] = await self._encryption.decrypt(value)
        return out

    async def encrypt_value(
        self, key_class: str, value: Any, *, deterministic: bool = False
    ) -> Binary:
        """For the equality queries deterministic fields exist to serve: the
        query term must be encrypted the same way the stored value was."""
        return await self._encryption.encrypt(
            value,
            DETERMINISTIC if deterministic else RANDOMIZED,
            key_id=self._key_for(key_class),
        )

    def _key_for(self, key_class: str) -> Binary:
        try:
            return self._keys[key_class]
        except KeyError:
            raise CsfleConfigurationError(
                f"no data key provisioned for class {key_class!r} — call provision() first"
            ) from None


async def build_crypto(client: MongoClient, settings: Settings) -> FieldCrypto | None:
    """Return a provisioned codec, or None when CSFLE is switched off.

    Off is a legitimate dev state (no key file, plaintext locally). It is not a
    legitimate production state, so the guard below is not a warning.
    """
    if not settings.csfle_enabled:
        if settings.environment not in DEV_ENVIRONMENTS:
            raise CsfleConfigurationError(
                f"CSFLE is disabled in environment {settings.environment!r} — §13 requires "
                "field-level encryption for the columns marked in §6.4"
            )
        return None
    crypto = FieldCrypto(client, build_provider(settings), settings.csfle_key_vault_namespace)
    await crypto.provision()
    return crypto


def encrypted_collections() -> tuple[CollectionSpec, ...]:
    return tuple(s for s in SPECS if s.encrypted)
