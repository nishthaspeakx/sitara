"use client";

/**
 * S29 You home — §29.1 `/you`, §24.1's fourth tab.
 *
 * ── It links to what exists, and says plainly what does not ───────────────
 *
 * §24.1 gives this tab six destinations: profile, family, memory vault,
 * subscription, settings, help. M10 built two — S25 `/you/memories` and S27
 * `/you/family` — and M11 added the third, S30 `/you/subscription`. Settings
 * (S35) and privacy (S36) still have no route.
 *
 * So there are three rows, not six. A row that navigated to a 404 would be
 * exactly the dead end §24.6 forbids, and a DISABLED row is worse than either:
 * `ErrorState`'s `retryable: false` rule already settles this shape for the
 * whole app — where an action cannot happen, no control for it exists at all,
 * because a greyed control still asserts the thing is nearly there.
 *
 * `you.later` is one honest sentence instead. It states what is coming without
 * pretending it is reachable — and it SHRINKS as routes land, which is the
 * half that is easy to forget: M11 built S30, so the sentence stopped naming
 * subscription in the same commit that added the row. A promise that something
 * "arrives in a later release" sitting beside a working link to it is the
 * honest-absence line gone stale, which is worse than never having had one.
 *
 * The counts are real reads, not decoration: §30.5 makes this tab the place a
 * person comes to find out what the app holds about her, and a link that said
 * "Memories" with no number would make her open it to learn nothing.
 */

import { CreditCard, Sparkles, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { ErrorState, ListRow, SectionHeader, Skeleton } from "@/components/ui";
import { ICON_STROKE } from "@/components/ui/_util";
import { useRouter } from "@/i18n/navigation";
import { loadMembers } from "@/lib/family";
import { loadVault } from "@/lib/vault";

type View =
  | { kind: "loading" }
  | { kind: "ready"; memories: number; family: number }
  | { kind: "error"; error: ErrorEnvelope };

export default function YouPage() {
  const t = useTranslations();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });

  const refresh = useCallback(async () => {
    const [vault, members] = await Promise.all([loadVault(), loadMembers()]);
    if (!vault.ok) {
      setView({ kind: "error", error: vault.error });
      return;
    }
    if (!members.ok) {
      setView({ kind: "error", error: members.error });
      return;
    }
    setView({ kind: "ready", memories: vault.data.length, family: members.data.length });
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <YouShell testId="you" titleKey="you.title" subtitleKey="you.subtitle">
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" ? (
        <>
          <SectionHeader level={2} titleKey="you.section_yours" />
          <ul className="flex flex-col">
            <li>
              <ListRow
                labelKey="you.memories"
                detail={t("you.memories_detail", { count: view.memories })}
                leading={<Sparkles strokeWidth={ICON_STROKE} />}
                onClick={() => router.push("/you/memories")}
              />
            </li>
            <li>
              <ListRow
                labelKey="you.family"
                detail={t("you.family_detail", { count: view.family })}
                leading={<Users strokeWidth={ICON_STROKE} />}
                onClick={() => router.push("/you/family")}
              />
            </li>
            {/* M11. The row exists because the route does — and `you.later`
                below dropped "subscription" in the same commit. A sentence
                that still promised it "in a later release" beside a working
                link is the honest-absence line gone stale, which is worse
                than never having had one. */}
            <li>
              <ListRow
                labelKey="you.subscription"
                detailKey="you.subscription_detail"
                leading={<CreditCard strokeWidth={ICON_STROKE} />}
                onClick={() => router.push("/you/subscription")}
              />
            </li>
          </ul>

          {/* Not a row, not a disabled control, not a "coming soon" badge —
              a sentence. See the file header. */}
          <p data-testid="you-later" className="pt-2 text-caption text-ink-muted">
            {t("you.later")}
          </p>
        </>
      ) : null}
    </YouShell>
  );
}
