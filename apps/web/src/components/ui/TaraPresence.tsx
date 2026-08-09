"use client";

/**
 * TaraPresence — §24.3 Sitara-specific. The portrait/cinemagraph host.
 *
 * Tara's likeness is AI-generated and exclusively owned — NOT a real person and
 * NOT a licensed human model (CC-008, superseding §25.2's baseline). She is
 * never called an avatar (glossary, §4). Rules this component enforces so a
 * screen cannot break them:
 *  · §25.2 — the "Tara · AI guide" disclosure is non-negotiable wherever her
 *    name or face appears. `showAiLabel` renders it, and CC-008 makes it
 *    mandatory rather than optional on the profile, call and chat headers.
 *  · §29.4 — the portrait is never cropped through the face (cover anchored to
 *    the top, matching how the assets were cropped), never flipped, never
 *    filtered beyond the graded masters.
 *  · §0.12 — the only loop she is allowed is her idle breathing. Under reduced
 *    motion the loop is not merely paused: the video is never mounted, and the
 *    still is the whole component. The delivered kit is stills only, so today
 *    every surface takes that path.
 *
 * Asset paths live only in `tara-assets.ts`.
 */

import tokens from "@sitara/tokens/tokens.json";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { TARA_ASSETS } from "./tara-assets";
import { cn, type TaraSize, type TaraState } from "./_util";

const SIZE: Record<TaraSize, string> = {
  sm: "h-presence-sm w-presence-sm rounded-portrait",
  md: "h-presence-md w-presence-md rounded-portrait",
  lg: "h-presence-lg w-presence-lg rounded-portrait",
  full: "h-full w-full rounded-none",
};

/**
 * Rendered CSS size per variant, so the browser picks the right candidate.
 * `sizes` must be a literal length — it cannot read a custom property — so the
 * values come from the token SOURCE rather than being retyped here. A change to
 * presence.sm moves the breakpoint hint with it.
 */
const SIZES_ATTR: Record<TaraSize, string> = {
  sm: tokens.presence.sm.value,
  md: tokens.presence.md.value,
  lg: tokens.presence.lg.value,
  full: "100vw",
};

export interface TaraPresenceProps {
  size?: TaraSize;
  state?: TaraState;
  /** Renders the §25.2 "Tara · AI guide" disclosure beneath the portrait. */
  showAiLabel?: boolean;
  /**
   * Forces the still. Reduced motion already does this; pass it for the
   * surfaces where §29.5 wants a still regardless (Today header, paywall).
   */
  still?: boolean;
  className?: string;
}

export function TaraPresence({
  size = "md",
  state = "warm_neutral",
  showAiLabel = false,
  still = false,
  className,
}: TaraPresenceProps) {
  const t = useTranslations();
  const asset = TARA_ASSETS[state];
  const [prefersReduced, setPrefersReduced] = useState(true);

  useEffect(() => {
    // Start from "reduced" so the first paint is never a loop we then have to
    // stop; the video only mounts once we know motion is welcome.
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const forced = document.documentElement.closest('[data-motion="reduced"]') !== null ||
      document.documentElement.getAttribute("data-motion") === "reduced";
    const update = () => setPrefersReduced(query.matches || forced);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const hasLoop = Boolean(asset.cinemagraphH265 || asset.cinemagraphVp9);
  const showVideo = hasLoop && !still && !prefersReduced;

  return (
    <figure className={cn("flex flex-col items-center gap-1", className)}>
      <div className={cn("overflow-hidden bg-brand-navy-deep", SIZE[size])}>
        {showVideo ? (
          <video
            autoPlay
            loop
            muted
            playsInline
            poster={asset.poster}
            aria-label={t(`ui.tara.state.${state}`)}
            /* object-top keeps the crop below the chin — never through the face */
            className="h-full w-full object-cover object-top"
          >
            {asset.cinemagraphH265 ? <source src={asset.cinemagraphH265} type="video/mp4" /> : null}
            {asset.cinemagraphVp9 ? <source src={asset.cinemagraphVp9} type="video/webm" /> : null}
          </video>
        ) : (
          /* The circular sizes take the square crops; the full-bleed call
             layout takes the portrait set. WebP first, JPEG for anything that
             cannot take it. */
          <picture>
            <source
              type="image/webp"
              srcSet={size === "full" ? asset.portraitWebp : asset.circleWebp}
              sizes={SIZES_ATTR[size]}
            />
            <source
              type="image/jpeg"
              srcSet={size === "full" ? asset.portraitJpeg : asset.circleJpeg}
              sizes={SIZES_ATTR[size]}
            />
            {/* <picture> owns the art direction here: next/image cannot express
                the circle-crop vs full-bleed split from one manifest entry. */}
            <img
              src={asset.poster}
              alt={t(`ui.tara.state.${state}`)}
              loading={size === "full" ? "eager" : "lazy"}
              decoding="async"
              className="h-full w-full object-cover object-top"
            />
          </picture>
        )}
      </div>
      {showAiLabel ? (
        <figcaption className="text-caption text-ink-muted">{t("ui.tara.ai_label")}</figcaption>
      ) : null}
    </figure>
  );
}
