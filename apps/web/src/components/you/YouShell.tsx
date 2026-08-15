"use client";

/**
 * The `/you` shell — §24.1's fourth tab.
 *
 * **`src/components/you/` is NOT the component library**, same rule as
 * `today/`, `ask/`, `call/` and `journal/`. §24.3 is fixed at 49 and
 * `tests/library.spec.ts` scans only `src/components/ui`.
 *
 * ── What the shell IS ─────────────────────────────────────────────────────
 *
 * §24.1: "You (profile, family, memory vault, subscription, settings, help)",
 * and "each tab keeps its own stack". So this is the chrome every surface in
 * that stack shares — the tab bar with `you` active, one title treatment, one
 * place the tab-switch route is written.
 *
 * `withTabs` is false on the two DETAIL surfaces (S26, S28). A tab bar is four
 * other exits, and both of those screens carry a destructive sheet: §29.1 makes
 * the same structural argument for the safety takeover, which renders no tab
 * bar for the same reason. On a detail screen the back control is the way out
 * and it is the only one that returns you to what you were looking at.
 */

import type { ReactNode } from "react";

import { Header, TabBar } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import type { MessageKey } from "@/components/ui/_util";

export interface YouShellProps {
  /** The surface's own testid — `you`, `vault`, `family`, `memory`, `member`. */
  testId: string;
  titleKey?: MessageKey;
  /** User data (a person's name) rather than a key — `Header`'s own convention. */
  title?: string;
  subtitleKey?: MessageKey;
  /** Trailing header controls. */
  actions?: ReactNode;
  /** False on the detail surfaces. See the header. */
  withTabs?: boolean;
  onBack?: () => void;
  children: ReactNode;
}

export function YouShell({
  testId,
  titleKey,
  title,
  subtitleKey,
  actions,
  withTabs = true,
  onBack,
  children,
}: YouShellProps) {
  const router = useRouter();
  return (
    <div data-testid={testId} className="flex min-h-screen flex-col bg-bg-canvas">
      <Header
        variant="titled"
        titleKey={titleKey}
        title={title}
        subtitleKey={subtitleKey}
        actions={actions}
        onBack={onBack}
      />
      <main className="flex flex-1 flex-col gap-4 px-5 pb-10 pt-4">{children}</main>
      {withTabs ? <TabBar active="you" onSelect={(tab) => router.push(`/${tab}`)} /> : null}
    </div>
  );
}
