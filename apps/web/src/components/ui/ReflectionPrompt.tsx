"use client";

/**
 * ReflectionPrompt — §24.3 Sitara-specific. The night-reflection question
 * (S24: three prompts, a tomorrow line, a close ceremony).
 *
 * Skipping is a first-class answer, not a smaller one (§29.2). There is no
 * streak, no count, nothing to break.
 */

import { useTranslations } from "next-intl";
import { useId } from "react";

import { Button } from "./Button";
import { Card } from "./Card";
import { cn, focusRing, type MessageKey } from "./_util";

export interface ReflectionPromptProps {
  /** The question, already localised. */
  prompt: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  onSkip?: () => void;
  submitKey?: MessageKey;
  /** 1-based, for "question 2 of 3". */
  index?: number;
  total?: number;
  className?: string;
}

export function ReflectionPrompt({
  prompt,
  value,
  onChange,
  onSubmit,
  onSkip,
  submitKey = "ui.reflection.save",
  index,
  total,
  className,
}: ReflectionPromptProps) {
  const t = useTranslations();
  const id = useId();

  return (
    <Card measure className={cn("flex flex-col gap-3", className)}>
      {index && total ? (
        <p className="text-caption text-ink-muted">
          {t("ui.reflection.position", { index, total })}
        </p>
      ) : null}
      <label htmlFor={id} className="font-serif text-h3 text-ink-primary">
        {prompt}
      </label>
      <textarea
        id={id}
        rows={4}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t("ui.reflection.placeholder")}
        className={cn(
          "w-full resize-y rounded-chip border border-border-strong bg-surface p-3 text-body text-ink-primary",
          "placeholder:text-ink-muted",
          focusRing,
        )}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={onSubmit} disabled={value.trim().length === 0}>
          {t(submitKey)}
        </Button>
        {onSkip ? (
          <Button variant="tertiary" onClick={onSkip}>
            {t("ui.reflection.skip")}
          </Button>
        ) : null}
      </div>
    </Card>
  );
}
