"use client";

/**
 * S26 Memory detail — §29.1 `/you/memories/[id]`.
 *
 * ── The row is found in the LIST, and that is the API's answer ─────────────
 *
 * `memory/router.py` serves list, accept, edit, mute, delete and the two scoped
 * effects. There is no `GET /v1/memories/{id}`. Calling one anyway would be a
 * client built on an endpoint the real service does not expose — it would pass
 * every test against a stub written to match this screen, and 404 in
 * production. `lib/vault.ts` records the trade; `findMemory` is the one place
 * the resolution happens.
 *
 * ── The two controls here are opposites and are drawn as opposites ─────────
 *
 * §30.5 gives "don't remember this" (mute: withheld from retrieval, kept in the
 * vault, REVERSIBLE) and deletion (hard, embedding included, not reversible).
 * They are one tap apart and one of them does not undo, so mute is an ordinary
 * inline control with its own explanatory line, and deletion goes through the
 * §30.5 confirm sheet like every other destructive act in the app.
 *
 * ── `source_state` is rendered, never inferred ────────────────────────────
 *
 * §30.5: deleting a conversation marks dependent memory sources "source
 * removed" — the memory survives, its provenance does not. The screen says
 * which of the two it is, because a memory with no visible provenance and a
 * memory whose provenance was destroyed look identical otherwise, and only one
 * of them is a thing that happened to her.
 */

import { useLocale, useTranslations } from "next-intl";
import { use, useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { ConfirmDeleteSheet } from "@/components/deletion/ConfirmDeleteSheet";
import { YouShell } from "@/components/you/YouShell";
import { Button, ErrorState, MemoryCard, Skeleton, Toggle } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatStamp } from "@/lib/dates";
import { findMemory, forgetMemory, loadVault, setMuted, type Memory } from "@/lib/vault";

type View =
  | { kind: "loading" }
  | { kind: "ready"; memory: Memory }
  | { kind: "missing" }
  | { kind: "error"; error: ErrorEnvelope };

export default function MemoryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [view, setView] = useState<View>({ kind: "loading" });
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<ErrorEnvelope | null>(null);

  const refresh = useCallback(async () => {
    const result = await loadVault();
    if (!result.ok) {
      setView({ kind: "error", error: result.error });
      return;
    }
    const memory = findMemory(result.data, id);
    // A memory she deleted a moment ago on another device is a MISSING row,
    // not an error — §24.6 has no dead ends, and blaming the user for a link
    // that was true yesterday is what a 404 does here.
    setView(memory ? { kind: "ready", memory } : { kind: "missing" });
  }, [id]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const source = view.kind === "ready" ? view.memory.source_state : "present";

  return (
    <YouShell
      testId="memory"
      titleKey="vault.title"
      withTabs={false}
      onBack={() => router.push("/you/memories")}
    >
      {view.kind === "loading" ? <Skeleton variant="list" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "missing" ? (
        <p data-testid="memory-missing" className="text-body text-ink-muted">
          {t("vault.not_found")}
        </p>
      ) : null}

      {view.kind === "ready" ? (
        <>
          <MemoryCard
            type={view.memory.type}
            content={view.memory.content}
            consentedOn={formatStamp(view.memory.consent_granted_at, locale)}
          />

          {/* §30.5's provenance line. `source` is a BARE identifier: i18n-lint
              matches the literal template text and cannot expand a member
              expression. */}
          <p data-testid="memory-source" className="text-caption text-ink-muted">
            {t(`vault.source.${source}`)}
          </p>

          {/* Reversible, and drawn as the ordinary control it is. */}
          <Toggle
            labelKey={view.memory.muted ? "vault.unmute" : "vault.mute"}
            descriptionKey="vault.mute_help"
            checked={view.memory.muted}
            onChange={async (next) => {
              const result = await setMuted(view.memory.memory_id, next);
              if (result.ok) setView({ kind: "ready", memory: result.data });
            }}
          />

          {/* Not reversible, and never reached without the §30.5 sheet. */}
          <Button
            variant="secondary"
            fullWidth
            data-testid="memory-forget"
            onClick={() => {
              setDeleteError(null);
              setConfirming(true);
            }}
          >
            {t("vault.forget")}
          </Button>
        </>
      ) : null}

      {confirming ? (
        <ConfirmDeleteSheet
          scope="memory"
          open
          onClose={() => setConfirming(false)}
          busy={busy}
          error={deleteError}
          onConfirm={async () => {
            setBusy(true);
            const result = await forgetMemory(id);
            setBusy(false);
            if (!result.ok) {
              setDeleteError(result.error);
              return;
            }
            setConfirming(false);
            // Back to the vault: the thing this screen was about no longer
            // exists, so staying here would render `vault.not_found` at a
            // route that now describes nothing.
            router.push("/you/memories");
          }}
        />
      ) : null}
    </YouShell>
  );
}
