"use client";

/**
 * S25 Memory Vault — §29.1 `/you/memories`, §30.5 and §32.4.
 *
 * §30.5: "the 11 typed facts with consent stamps — never a content archive."
 * Both halves are structural here:
 *
 * **The 11 types are §32.4's, from the schema.** `MEMORY_TYPES` comes from
 * `@sitara/schemas`, and §32.4 ends "Vault filters use exactly these 11 labels,
 * localized" — so the filter set cannot drift from what the memory module
 * actually writes. It HAD drifted once, in `MemoryCard`: this file's ancestor
 * declared a different eleven and nothing failed, because no screen had ever
 * rendered a typed memory.
 *
 * **Muted and decayed rows are SHOWN.** This is the user's inventory of what
 * Tara knows, not a retrieval ranking. A vault that hid the memories Tara is
 * not currently using would be a vault that cannot be audited, which is the one
 * thing it is for. `vault.muted` marks them instead.
 */

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import type { ErrorEnvelope } from "@sitara/schemas";

import { YouShell } from "@/components/you/YouShell";
import { Chip, EmptyState, ErrorState, MemoryCard, Skeleton } from "@/components/ui";
import { useRouter } from "@/i18n/navigation";
import { formatStamp } from "@/lib/dates";
import { MEMORY_TYPES, loadVault, type Memory, type MemoryType } from "@/lib/vault";

type View =
  | { kind: "loading" }
  | { kind: "ready"; memories: Memory[] }
  | { kind: "error"; error: ErrorEnvelope };

export default function VaultPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const [filter, setFilter] = useState<MemoryType | "all">("all");
  const [view, setView] = useState<View>({ kind: "loading" });

  const refresh = useCallback(async () => {
    // The filter is a QUERY PARAMETER, not a client-side `.filter()`. §32.4
    // gives types 7–9 visibility gates the server owns; a client that filtered
    // a full list would be a second implementation of which memories may be
    // shown, and the two would disagree exactly where it matters.
    const result = await loadVault(filter === "all" ? [] : [filter]);
    setView(
      result.ok ? { kind: "ready", memories: result.data } : { kind: "error", error: result.error },
    );
  }, [filter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <YouShell testId="vault" titleKey="vault.title" subtitleKey="vault.subtitle">
      <fieldset>
        <legend className="pb-2 text-caption text-ink-muted">{t("vault.filter_label")}</legend>
        <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1">
          <Chip variant="filter" selected={filter === "all"} onClick={() => setFilter("all")}>
            {t("vault.filter_all")}
          </Chip>
          {MEMORY_TYPES.map((type) => (
            <Chip
              key={type}
              variant="filter"
              selected={filter === type}
              onClick={() => setFilter(type)}
            >
              {t(`ui.memory.type.${type}`)}
            </Chip>
          ))}
        </div>
      </fieldset>

      {view.kind === "loading" ? <Skeleton variant="list" /> : null}

      {view.kind === "error" ? (
        <ErrorState error={view.error} onRetry={() => void refresh()} />
      ) : null}

      {view.kind === "ready" ? (
        <>
          <p data-testid="vault-count" className="text-caption text-ink-muted">
            {t("vault.count", { count: view.memories.length })}
          </p>

          {view.memories.length === 0 ? (
            <div className="flex flex-1 items-center justify-center">
              <EmptyState id="memories" onAction={() => router.push("/ask")} />
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {view.memories.map((memory) => (
                <li
                  key={memory.memory_id}
                  data-testid="memory-row"
                  data-memory-id={memory.memory_id}
                  data-muted={memory.muted ? "true" : "false"}
                >
                  <MemoryCard
                    type={memory.type}
                    content={memory.content}
                    // Formatted in the user's locale, numerals included (§2.4).
                    // A raw ISO string is a machine's idea of a day.
                    consentedOn={formatStamp(memory.consent_granted_at, locale)}
                    onOpen={() => router.push(`/you/memories/${memory.memory_id}`)}
                  />
                  {memory.muted ? (
                    <p className="px-1 pt-1 text-caption text-ink-muted">{t("vault.muted")}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </YouShell>
  );
}
