/** Tailwind wired to @sitara/tokens (SPEC §24.2) — token-only styling. */
const preset = require("@sitara/tokens/tailwind-preset");
const plugin = require("tailwindcss/plugin");

/** @type {import('tailwindcss').Config} */
module.exports = {
  presets: [preset],
  content: ["./src/**/*.{ts,tsx}", "./.storybook/**/*.{ts,tsx}"],
  plugins: [
    plugin(({ addVariant }) => {
      // §0.12 — every animation has a reduced-motion equivalent. `motion-reduce:`
      // follows the OS setting; `motion-off:` follows the [data-motion="reduced"]
      // hook so Storybook and the screenshot suite can force the same path.
      addVariant("motion-off", '[data-motion="reduced"] &');
      // §24.2 per-script tuning is applied by [data-script]; this variant is for
      // the rare case a component needs to rearrange, not just re-measure.
      addVariant("script-tamil", '[data-script="tamil"] &');
      addVariant("script-telugu", '[data-script="telugu"] &');
      addVariant("script-devanagari", '[data-script="devanagari"] &');
    }),
  ],
};
