/**
 * SPEC §24.2 / §29.4 — token build: src/tokens.json (single source) →
 *   dist/css/tokens.css        (:root light vars, [data-theme="night"] overrides,
 *                               [data-script] typography blocks, reduced-motion collapse)
 *   dist/tailwind.preset.cjs   (Tailwind theme mapped to the CSS vars)
 *
 * Pipeline per spec: Figma variables → Style Dictionary → Tailwind config + CSS custom properties.
 */
import StyleDictionary from "style-dictionary";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));

/** The six scripts the eight launch languages are written in (§2.3, §24.2). */
const SCRIPTS = ["latin", "devanagari", "gujarati", "gurmukhi", "tamil", "telugu"];

/** css var name for a token path, with the theme segment stripped for colors:
 *  color.light.bg.canvas → --color-bg-canvas ; color.night.gold → --color-gold */
function varName(token) {
  const p = [...token.path];
  if (p[0] === "color" && (p[1] === "light" || p[1] === "night")) p.splice(1, 1);
  return `--${p.join("-")}`;
}

StyleDictionary.registerFormat({
  name: "sitara/css-themed",
  format: ({ dictionary }) => {
    const light = [];
    const night = [];
    const common = [];
    for (const t of dictionary.allTokens) {
      // §24.2: the per-script size factor is part of the scale, not a per-component
      // override — every text utility is script-tuned by construction.
      const value =
        t.path[0] === "font" && t.path[1] === "size"
          ? `calc(${t.value} * var(--font-script-size-factor, 1))`
          : t.value;
      const line = `  ${varName(t)}: ${value};`;
      if (t.path[0] === "color" && t.path[1] === "night") night.push(line);
      else if (t.path[0] === "color" && t.path[1] === "light") light.push(line);
      else common.push(line);
    }

    /** §24.2: per-script overrides are tokens. [data-script] rebinds the active
     *  alias vars, so one `.script-tuned` rule serves every script. */
    const byScript = (name) => {
      const get = (p) =>
        dictionary.allTokens.find((t) => t.path.join(".") === p)?.value;
      return [
        `  --font-family-script: var(--font-family-script-${name});`,
        `  --font-script-size-factor: ${get(`font.script.${name}.size-factor`)};`,
        `  --font-script-line-height: ${get(`font.script.${name}.line-height`)};`,
        `  --font-script-letter-spacing: ${get(`font.script.${name}.letter-spacing`)};`,
      ].join("\n");
    };

    const scriptBlocks = SCRIPTS.map((s) =>
      s === "latin"
        ? `:root,\n[data-script="latin"] {\n${byScript(s)}\n}`
        : `[data-script="${s}"] {\n${byScript(s)}\n}`,
    );

    /** §0.12: every animation has a reduced-motion equivalent. Collapsing the
     *  duration tokens gives every token-only component that equivalent for free.
     *  [data-motion="reduced"] is the forced hook (Storybook / screenshot suite). */
    const reduced = [
      "  --motion-duration-standard: 0.01ms;",
      "  --motion-duration-enter: 0.01ms;",
      "  --motion-duration-exit: 0.01ms;",
      "  --motion-duration-ceremony: 0.01ms;",
      "  --motion-standard: 0.01ms linear;",
      "  --motion-enter: 0.01ms linear;",
      "  --motion-exit: 0.01ms linear;",
      "  --motion-ceremony: 0.01ms linear;",
    ].join("\n");

    return [
      "/* GENERATED — do not edit. Source: packages/tokens/src/tokens.json (SPEC §24.2/§29.4). */",
      ":root {",
      "  color-scheme: light;",
      ...light,
      ...common,
      "}",
      "",
      '[data-theme="night"] {',
      "  color-scheme: dark;",
      ...night,
      "}",
      "",
      "/* Per-script typography (§24.2) — Noto family + tuned size/leading/tracking. */",
      ...scriptBlocks,
      "",
      "/* Reduced motion (§0.12). */",
      "@media (prefers-reduced-motion: reduce) {",
      "  :root {",
      reduced.replace(/^ {2}/gm, "    "),
      "  }",
      "}",
      '[data-motion="reduced"] {',
      reduced,
      "}",
      "",
    ].join("\n");
  },
});

StyleDictionary.registerFormat({
  name: "sitara/tailwind-preset",
  format: ({ dictionary }) => {
    const colors = {};
    const spacing = {};
    const borderRadius = {};
    const boxShadow = {};
    const fontSize = {};
    const fontFamily = {};
    const maxWidth = {};
    const screens = {};
    const transitionDuration = {};
    const transitionTimingFunction = {};
    const transitionProperty = {};
    for (const t of dictionary.allTokens) {
      const ref = `var(${varName(t)})`;
      const [cat, ...rest] = t.path;
      if (cat === "color" && t.path[1] === "light") {
        colors[rest.slice(1).join("-")] = ref;
        // `text-on-brand` reads better than `text-text-on-brand`; the on-* and
        // inverse leaves are unambiguous, so they get a short alias too.
        if (rest[1] === "text" && /^(on-brand|on-gold|inverse)$/.test(rest[2])) {
          colors[rest[2]] = ref;
        }
      } else if (cat === "color" && t.path[1] === "night") {
        // night values override the same vars at runtime; only night-exclusive
        // names (e.g. candle) need their own utility entry.
        const key = rest.slice(1).join("-");
        if (!(key in colors)) colors[key] = ref;
      } else if (cat === "space") {
        spacing[rest.join("-")] = ref;
      } else if (cat === "radius") {
        borderRadius[rest.join("-")] = ref;
      } else if (cat === "elevation") {
        boxShadow[rest.join("-")] = ref;
      } else if (cat === "font" && rest[0] === "size") {
        // tuple form: every text utility carries the active script's leading and
        // tracking (§24.2 per-script overrides are tokens, not hacks)
        fontSize[rest.slice(1).join("-")] = [
          ref,
          {
            lineHeight: "var(--font-script-line-height)",
            letterSpacing: "var(--font-script-letter-spacing)",
          },
        ];
      } else if (cat === "font" && rest[0] === "family") {
        fontFamily[rest.slice(1).join("-")] = t.value.split(",").map((s) => s.trim());
      } else if (cat === "font" && rest[0] === "measure") {
        maxWidth[rest.slice(1).join("-")] = ref;
      } else if (cat === "breakpoint") {
        // media queries cannot read custom properties — literal values only
        screens[rest.join("-")] = t.value;
      } else if (cat === "motion" && rest[0] === "duration") {
        transitionDuration[rest.slice(1).join("-")] = ref;
      } else if (cat === "motion" && rest[0] === "easing") {
        transitionTimingFunction[rest.slice(1).join("-")] = ref;
      } else if (cat === "touch" || cat === "control" || cat === "presence") {
        spacing[`${cat}-${rest.join("-")}`] = ref;
      } else if (cat === "focus" && rest[0] === "shadow") {
        boxShadow["focus"] = ref;
      } else if (cat === "focus") {
        spacing[`focus-${rest.join("-")}`] = ref;
      }
    }
    // `colors` replaces Tailwind's palette wholesale, so the keywords every
    // utility family assumes have to be restated.
    Object.assign(colors, {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
    });
    // the script families are addressable as font-script-tamil etc.; the ACTIVE
    // one follows [data-script] through the alias var.
    fontFamily["script"] = ["var(--font-family-script)"];

    const j = (o) => JSON.stringify(o, null, 6).replace(/\n\}/, "\n    }");
    return [
      "/* GENERATED — do not edit. Source: packages/tokens/src/tokens.json (SPEC §24.2/§29.4). */",
      "module.exports = {",
      "  theme: {",
      `    colors: ${j(colors)},`,
      `    screens: ${j(screens)},`,
      `    extend: {`,
      `      spacing: ${JSON.stringify(spacing)},`,
      `      borderRadius: ${JSON.stringify(borderRadius)},`,
      `      boxShadow: ${JSON.stringify(boxShadow)},`,
      `      fontSize: ${JSON.stringify(fontSize)},`,
      `      fontFamily: ${JSON.stringify(fontFamily)},`,
      `      maxWidth: ${JSON.stringify(maxWidth)},`,
      `      transitionDuration: ${JSON.stringify(transitionDuration)},`,
      `      transitionTimingFunction: ${JSON.stringify(transitionTimingFunction)},`,
      `      transitionProperty: ${JSON.stringify(transitionProperty)},`,
      `      outlineWidth: { focus: "var(--focus-ring-width)" },`,
      `      outlineOffset: { focus: "var(--focus-ring-offset)" },`,
      `      borderWidth: { focus: "var(--focus-ring-width)", "presence-ring": "var(--presence-ring)" },`,
      `      lineHeight: { script: "var(--font-script-line-height)" },`,
      `      letterSpacing: { script: "var(--font-script-letter-spacing)" },`,
      "    },",
      "  },",
      "};",
      "",
    ].join("\n");
  },
});

const sd = new StyleDictionary({
  source: [path.join(here, "src/tokens.json")],
  platforms: {
    css: {
      buildPath: path.join(here, "dist/css/"),
      files: [{ destination: "tokens.css", format: "sitara/css-themed" }],
    },
    tailwind: {
      buildPath: path.join(here, "dist/"),
      files: [{ destination: "tailwind.preset.cjs", format: "sitara/tailwind-preset" }],
    },
  },
  log: { verbosity: "silent" },
});

await sd.buildAllPlatforms();
console.log("built: dist/css/tokens.css, dist/tailwind.preset.cjs");
