import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { DIST_DIRS } from "./scripts/dist-dirs.mjs";

const compat = new FlatCompat({
  baseDirectory: path.dirname(fileURLToPath(import.meta.url)),
});

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      // Sourced from the one definition rather than listed here: adding a
      // fourth output directory and forgetting to ignore it means eslint
      // lints a build, which surfaces as thousands of errors in generated
      // code and reads like the source is broken.
      ...Object.values(DIST_DIRS).map((dir) => `${dir}/**`),
      "node_modules/**",
      "next-env.d.ts",
      "*.cjs",
      // build outputs, not source
      "storybook-static/**",
      "test-results/**",
      "playwright-report/**",
    ],
  },
];

export default config;
