"use client";

/**
 * S14 Today — the destination, NOT the screen.
 *
 * §28.2 specifies Today in full: sixteen variants, three densities, the
 * core-card dominance rule, a p95 render budget. None of that is M8's, and
 * building a plausible-looking approximation of it would be worse than this —
 * a screen that looks finished is a screen nobody revisits.
 *
 * So this is an honest placeholder: the onboarding stack has to land somewhere
 * (§28.1: "onboarding … never exits to blank"), and the flow tests assert that
 * it lands here. It uses the §24.3 library like every other screen, states what
 * it is, and offers the one thing that already exists.
 */

import { EmptyState, Header, TabBar } from "@/components/ui";

export default function TodayPage() {
  return (
    <div className="flex min-h-screen flex-col bg-bg-canvas" data-testid="today">
      <Header variant="titled" titleKey="ui.tabs.today" />
      <main className="flex flex-1 items-center justify-center px-6">
        {/* The pre-first-brief empty state (§28.2's first-session variant is
            M9's; this is the designed empty state that already exists). */}
        <EmptyState id="saved_guidance" />
      </main>
      <TabBar active="today" onSelect={() => undefined} />
    </div>
  );
}
