"use client";

/**
 * S14 Today — §28.2, wired to §7.1's pipeline.
 *
 * This file is the state machine and nothing else: fetch, decide which of the
 * three outcomes we are in, hand a resolved payload to `TodayScreen`. Every
 * substantive rule lives somewhere it can be tested without a browser —
 * §32.1's precedence in `lib/today-variant.ts`, the anatomy in `TodayScreen`,
 * the sentences in the API.
 *
 * **A failed fetch is a screen, not an error.** §28.2 has a designed variant
 * for it ("Offline: cached brief + offline banner; practical strip marked 'as
 * of [time]'"), so a §34.4 envelope with a cached payload behind it renders
 * Today, offline. `ErrorState` is reserved for the one case §28.2 does not
 * cover: no brief and nothing cached, on the app's home surface, which is the
 * only honest thing left to show.
 */

import { useEffect, useState } from "react";

import type { ErrorEnvelope, TodayPayload } from "@sitara/schemas";

import { ErrorState, Skeleton } from "@/components/ui";
import { TodayScreen } from "@/components/today/TodayScreen";
import { useRouter } from "@/i18n/navigation";
import { fetchToday, readCachedToday } from "@/lib/today";
import { resolveChrome } from "@/lib/today-variant";

type State =
  | { kind: "loading" }
  | { kind: "ready"; payload: TodayPayload; offline: boolean; cachedAt?: string }
  | { kind: "error"; error: ErrorEnvelope };

export default function TodayPage() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await fetchToday();
      if (cancelled) return;
      if (result.ok) {
        setState({ kind: "ready", payload: result.data, offline: false });
        return;
      }
      // §28.2's offline variant. The cached brief is a real brief that was
      // true when it was taken, which is why it is shown with its age rather
      // than withheld.
      const cached = readCachedToday();
      setState(
        cached
          ? {
              kind: "ready",
              payload: cached.payload,
              offline: true,
              cachedAt: cached.cachedAt,
            }
          : { kind: "error", error: result.error },
      );
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "loading") {
    // §28.2: "loading = skeleton mirroring anatomy". Not a spinner — the shape
    // of what is coming is what makes a wait feel short.
    return (
      <div data-testid="today" data-variant="loading" className="flex min-h-app flex-col gap-5 bg-bg-canvas p-5">
        <Skeleton variant="brief" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div data-testid="today" data-variant="error" className="flex min-h-app items-center justify-center bg-bg-canvas p-5">
        <ErrorState error={state.error} onRetry={() => router.refresh()} />
      </div>
    );
  }

  const chrome = resolveChrome({
    state: state.payload.state,
    localTime: state.payload.local_time,
    status: state.payload.status,
    offline: state.offline,
  });

  return (
    <TodayScreen
      payload={state.payload}
      chrome={chrome}
      cachedAt={state.cachedAt}
      onSelectTab={(tab) => router.push(`/${tab}`)}
      // B2. No conversation id here: Today is not a thread, so the call opens
      // on the account's shared session conversation exactly as a direct visit
      // to /ask/call does. B1's header entry is the one that CARRIES a thread.
      onCallTara={() => router.push("/ask/call")}
    />
  );
}
