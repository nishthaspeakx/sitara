/**
 * SPEC §24.2 — token build: src/tokens.json (single source) →
 *   dist/css/tokens.css        (:root light vars + [data-theme="night"] overrides)
 *   dist/tailwind.preset.cjs   (Tailwind theme mapped to the CSS vars)
 *
 * Pipeline per spec: Figma variables → Style Dictionary → Tailwind config.
 */
import StyleDictionary from "style-dictionary";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));

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
      const line = `  ${varName(t)}: ${t.value};`;
      if (t.path[0] === "color" && t.path[1] === "night") night.push(line);
      else if (t.path[0] === "color" && t.path[1] === "light") light.push(line);
      else common.push(line);
    }
    return [
      "/* GENERATED — do not edit. Source: packages/tokens/src/tokens.json (SPEC §24.2). */",
      ":root {",
      ...light,
      ...common,
      "}",
      "",
      '[data-theme="night"] {',
      ...night,
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
    const transition = {};
    for (const t of dictionary.allTokens) {
      const ref = `var(${varName(t)})`;
      const [cat, ...rest] = t.path;
      if (cat === "color" && t.path[1] === "light") {
        colors[rest.slice(1).join("-")] = ref;
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
        fontSize[rest.slice(1).join("-")] = ref;
      } else if (cat === "font" && rest[0] === "family") {
        fontFamily[rest.slice(1).join("-")] = t.value.split(",").map((s) => s.trim());
      } else if (cat === "motion") {
        transition[rest.join("-")] = ref;
      }
    }
    return [
      "/* GENERATED — do not edit. Source: packages/tokens/src/tokens.json (SPEC §24.2). */",
      "module.exports = {",
      "  theme: {",
      `    colors: ${JSON.stringify(colors, null, 6).replace(/\n}/, "\n    }")},`,
      `    extend: {`,
      `      spacing: ${JSON.stringify(spacing)},`,
      `      borderRadius: ${JSON.stringify(borderRadius)},`,
      `      boxShadow: ${JSON.stringify(boxShadow)},`,
      `      fontSize: ${JSON.stringify(fontSize)},`,
      `      fontFamily: ${JSON.stringify(fontFamily)},`,
      `      transitionDuration: {},`,
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
