"use client";

/**
 * §28.2's first-session "brief-time edit".
 *
 * The control is the §24.3 `Slider`, whose own contract names this exact use
 * ("Slider (brief-time)") — so the picker is a Sheet around it rather than a
 * new control. §24.4 already established the 15-minute grain at S12; this is
 * the same decision surfaced again where §28.2 asks for it, not a second one.
 *
 * §29.2: the close control is always visible (`Sheet` renders it), there is no
 * countdown, and dismissing without saving changes nothing.
 */

import { useState } from "react";

import { Button, Sheet, Slider } from "@/components/ui";

/** 15-minute steps — the grain S12's picker uses. */
const STEP_MINUTES = 15;

export function minutesToHhmm(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function hhmmToMinutes(value: string): number {
  const [h, m] = value.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

export function BriefTimePicker({
  open,
  value,
  onClose,
  onSave,
}: {
  open: boolean;
  /** Zero-padded local "HH:MM" — the padding is load-bearing upstream (§7.1). */
  value: string;
  onClose: () => void;
  onSave?: (value: string) => void;
}) {
  const [minutes, setMinutes] = useState(() => hhmmToMinutes(value));

  return (
    <Sheet
      open={open}
      onClose={onClose}
      titleKey="today.brief_time.title"
      footer={
        <Button
          onClick={() => {
            onSave?.(minutesToHhmm(minutes));
            onClose();
          }}
        >
          {/* the Sheet's own close stays visible beside it (§29.2) */}
          <span data-testid="brief-time-save">{minutesToHhmm(minutes)}</span>
        </Button>
      }
    >
      <div data-testid="brief-time-picker" className="py-2">
        <Slider
          labelKey="today.brief_time.label"
          min={0}
          max={24 * 60 - STEP_MINUTES}
          step={STEP_MINUTES}
          value={minutes}
          onChange={setMinutes}
          format={minutesToHhmm}
        />
      </div>
    </Sheet>
  );
}
