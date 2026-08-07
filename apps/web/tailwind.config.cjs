/** Tailwind wired to @sitara/tokens (SPEC §24.2) — token-only styling. */
const preset = require("@sitara/tokens/tailwind-preset");

/** @type {import('tailwindcss').Config} */
module.exports = {
  presets: [preset],
  content: ["./src/**/*.{ts,tsx}"],
};
