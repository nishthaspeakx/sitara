import type { StorybookConfig } from "@storybook/nextjs";

/**
 * Storybook for the §24.3 component library.
 *
 * §24.8: "the per-locale screenshot-diff suite (§14) runs on component stories
 * (Storybook) AND full screens." This config is the component half; the stories
 * it collects are what the Playwright suite drives.
 */
const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-docs", "@storybook/addon-a11y"],
  framework: {
    name: "@storybook/nextjs",
    options: {},
  },
  // the Tara placeholder posters live in public/tara/placeholder
  staticDirs: ["../public"],
  typescript: {
    reactDocgen: "react-docgen-typescript",
  },
};

export default config;
