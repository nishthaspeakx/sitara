"""Generate the VAPID keypair (§6.2, RFC 8292). Run once, per environment.

    uv run python -m sitara_api.notifications.vapid --generate
    uv run python -m sitara_api.notifications.vapid --show

This is the whole "setup" web push has. There is no account to create, no
sender to verify, no vendor to bill: RFC 8292 authenticates a push sender with
a keypair it generates itself, and the push service is whichever one the user's
browser already uses. That is the property that let §6.2 choose web push, and
it is why this file is a `--generate` flag rather than a runbook.

── Why it is not generated at boot ─────────────────────────────────────────

A browser subscription is bound to the `applicationServerKey` it was created
with. Generate a new keypair and every subscription already in the database
becomes undeliverable — the push services answer 403, which
`webpush.py` correctly classifies as REJECTED rather than as a dead token, so
nothing self-heals and every user has to re-subscribe. Persisting it, once,
deliberately, is the only safe shape.

── Rotation ────────────────────────────────────────────────────────────────

Rotating a VAPID key is therefore a migration, not an operation: it needs both
keys live while clients re-subscribe. That is out of scope here and
`--generate` refuses to overwrite an existing file for exactly that reason —
the destructive version of this command is one `>` away and its blast radius
is every push subscription in the product.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sitara_api.config import Settings
from sitara_api.notifications.providers.registry import vapid_path
from sitara_api.notifications.providers.webpush import VapidKeypair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VAPID keypair for §6.2 web push")
    parser.add_argument(
        "--generate", action="store_true", help="Create a keypair if none exists"
    )
    parser.add_argument(
        "--show", action="store_true", help="Print the public key (safe to share)"
    )
    parser.add_argument("--path", help="Override the key file location")
    args = parser.parse_args(argv)

    settings = Settings()
    path = Path(args.path) if args.path else vapid_path(settings)
    if path is None:
        print("no vapid path configured", file=sys.stderr)
        return 1

    if args.generate:
        if path.exists():
            # Refuses rather than prompts. See the module header: overwriting
            # this file invalidates every push subscription in the database,
            # and a y/n prompt is a thing people answer without reading.
            print(
                f"{path} already exists — refusing to overwrite.\n"
                "Replacing a VAPID keypair invalidates EVERY browser subscription "
                "already stored (a subscription is bound to the applicationServerKey "
                "it was created with). Rotating one is a migration that needs both "
                "keys live while clients re-subscribe, not a regenerate.",
                file=sys.stderr,
            )
            return 1
        keypair = VapidKeypair.generate(subject=settings.vapid_subject)
        keypair.save(path)
        print(f"wrote {path} (mode 600)")
        print(f"public key: {keypair.public_key_b64}")
        print(
            "\nThe public key is served to browsers by "
            "`GET /v1/notifications/push/key` — it is public by design and is what "
            "`pushManager.subscribe` needs."
        )
        return 0

    if not path.exists():
        print(f"no keypair at {path} — run with --generate", file=sys.stderr)
        return 1

    keypair = VapidKeypair.load(path)
    print(keypair.public_key_b64 if args.show else f"keypair present at {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
