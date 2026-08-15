import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/glaze-foundation.css", import.meta.url), "utf8");
const main = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");

const requiredCss = [
  "--glaze-touch-target: 44px",
  "--glaze-focus-ring:",
  "@media (hover: hover) and (pointer: fine)",
  "@media (hover: none), (pointer: coarse)",
  "@media (prefers-reduced-motion: reduce)",
  ".account-security-launcher",
  ".editor-actions button",
  ".nav-item",
];

for (const requirement of requiredCss) {
  if (!css.includes(requirement)) {
    throw new Error(`Missing Glaze foundation requirement: ${requirement}`);
  }
}

const importLine = 'import "./glaze-foundation.css";';
if (!main.includes(importLine)) {
  throw new Error("The shared Glaze foundation stylesheet is not loaded by the application entry point.");
}

const styleImports = [...main.matchAll(/^import "\.\/.+\.css";$/gm)].map((match) => match[0]);
if (styleImports.at(-1) !== importLine) {
  throw new Error("The shared Glaze foundation must load after component styles so accessibility overrides remain effective.");
}

console.log("Glaze UI interaction foundation validated.");
