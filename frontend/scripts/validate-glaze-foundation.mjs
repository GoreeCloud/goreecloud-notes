import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const EXPECTED_GLAZE_VERSION = "1.0.0";
const EXPECTED_GLAZE_REVISION = "d6e446fd8ef251259d16368d50aad90d9287a774";
const EXPECTED_GLAZE_BLOBS = {
  "glaze.css": "5bfc2b492627a160537182a0b01b67303540fd90",
  "glaze.accessibility.css": "e220590037e0edf9a32402cdd44640d7ed731eca",
  LICENSE: "1ca5ac91dfb32202f113f4686d593d127fafde11",
};

function read(relativePath) {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

function gitBlobSha(content) {
  const body = Buffer.from(content, "utf8");
  return createHash("sha1")
    .update(`blob ${body.byteLength}\0`, "utf8")
    .update(body)
    .digest("hex");
}

function requireIncludes(name, content, requirements) {
  for (const requirement of requirements) {
    if (!content.includes(requirement)) {
      throw new Error(`${name} is missing Glaze requirement: ${requirement}`);
    }
  }
}

const canonicalCss = read("../src/glaze/glaze.css");
const canonicalAccessibility = read("../src/glaze/glaze.accessibility.css");
const canonicalLicense = read("../src/glaze/LICENSE");
const sourceRecord = read("../src/glaze/SOURCE.md");
const themeBridge = read("../src/glaze-theme-bridge.css");
const notesFoundation = read("../src/glaze-foundation.css");
const main = read("../src/main.tsx");
const appearance = read("../src/appearance.ts");
const appearanceControl = read("../src/AppearanceControl.tsx");
const conformance = read("../../docs/glaze-ui-conformance.md");

const canonicalSnapshots = {
  "glaze.css": canonicalCss,
  "glaze.accessibility.css": canonicalAccessibility,
  LICENSE: canonicalLicense,
};
for (const [fileName, expectedSha] of Object.entries(EXPECTED_GLAZE_BLOBS)) {
  const actualSha = gitBlobSha(canonicalSnapshots[fileName]);
  if (actualSha !== expectedSha) {
    throw new Error(
      `${fileName} no longer matches the recorded canonical Glaze UI ${EXPECTED_GLAZE_VERSION} snapshot: expected ${expectedSha}, got ${actualSha}`,
    );
  }
}

requireIncludes("canonical glaze.css", canonicalCss, [
  "--glaze-canvas:",
  "--glaze-surface-strong:",
  "--glaze-accent:",
  "--glaze-danger:",
  "--glaze-target-min: 44px",
  "--glaze-motion-instant: 90ms",
  "--glaze-motion-fast: 160ms",
  "--glaze-motion-standard: 220ms",
  "--glaze-motion-emphasized: 320ms",
  ".glaze-surface-solid",
  ".glaze-surface-raised",
  ".glaze-surface",
  ".glaze-overlay",
  "@media (max-width: 599px)",
  "@media (min-width: 600px) and (max-width: 1023px)",
  "@media (min-width: 1024px) and (max-width: 1439px)",
  "@media (min-width: 1440px)",
]);

requireIncludes("canonical accessibility", canonicalAccessibility, [
  "@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))",
  "@media (prefers-reduced-transparency: reduce)",
  "@media (prefers-reduced-motion: reduce)",
  "@media (prefers-contrast: more)",
  "@media (forced-colors: active)",
]);

requireIncludes("canonical Glaze license", canonicalLicense, [
  "MIT License",
  "Copyright (c) 2026 GoreeCloud",
  "The above copyright notice and this permission notice shall be included",
]);

requireIncludes("Glaze source record", sourceRecord, [
  `Glaze UI version: \`${EXPECTED_GLAZE_VERSION}\``,
  `Canonical revision: \`${EXPECTED_GLAZE_REVISION}\``,
  "byte-for-byte copies",
  "Canonical license: MIT",
]);

requireIncludes("theme compatibility bridge", themeBridge, [
  "explicit System/Light/Dark",
  ".account-security-page",
  'root[data-theme="light"]',
  'root[data-theme="dark"]',
  "var(--glaze-canvas)",
]);

requireIncludes("Notes Glaze foundation", notesFoundation, [
  "GoreeCloud Notes product mapping for Glaze UI 1.0.0",
  "var(--glaze-surface)",
  "var(--glaze-surface-strong)",
  "var(--glaze-shadow-raised)",
  "var(--glaze-motion-fast)",
  "var(--glaze-motion-standard)",
  ".glaze-utility-dock",
  ".appearance-control",
  "@media (hover: hover) and (pointer: fine)",
  "@media (hover: none), (pointer: coarse)",
  "@media (max-width: 599px)",
  "@media (min-width: 600px) and (max-width: 1023px)",
  "@media (min-width: 1024px) and (max-width: 1439px)",
  "@media (min-width: 1440px)",
  "@media (prefers-reduced-transparency: reduce)",
  "@media (prefers-contrast: more)",
  "@media (forced-colors: active)",
  "@media (prefers-reduced-motion: reduce)",
  "@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))",
]);

requireIncludes("appearance behavior", appearance, [
  'export type AppearancePreference = "system" | "light" | "dark"',
  'goreecloud.notes.appearance',
  'root.removeAttribute("data-theme")',
  "root.dataset.theme = preference",
  "window.localStorage",
]);

requireIncludes("appearance control", appearanceControl, [
  'value: "system"',
  'value: "light"',
  'value: "dark"',
  'className="glaze-select appearance-select"',
  'aria-label="Appearance"',
  'window.addEventListener("storage", handleStorage)',
  "applyAppearancePreference(nextPreference)",
]);

const expectedStyleOrder = [
  'import "./glaze/glaze.css";',
  'import "./glaze/glaze.accessibility.css";',
  'import "./styles.css";',
  'import "./organization.css";',
  'import "./rich-editor.css";',
  'import "./attachments.css";',
  'import "./account-security.css";',
  'import "./glaze-theme-bridge.css";',
  'import "./glaze-foundation.css";',
];

const styleImports = [...main.matchAll(/^import "\.\/.+\.css";$/gm)].map((match) => match[0]);
if (JSON.stringify(styleImports) !== JSON.stringify(expectedStyleOrder)) {
  throw new Error(`Unexpected Glaze/product stylesheet order: ${styleImports.join(", ")}`);
}

requireIncludes("application entry point", main, [
  "initializeAppearancePreference();",
  'className="notes-root glaze-canvas"',
  'className="glaze-utility-dock glaze-overlay"',
  "<AppearanceControl />",
  'className="account-security-launcher glaze-button"',
]);

requireIncludes("Glaze conformance record", conformance, [
  "Glaze UI 1.0.0",
  EXPECTED_GLAZE_REVISION,
  "Compact: through 599 px",
  "Medium: 600–1023 px",
  "Expanded: 1024–1439 px",
  "Wide: 1440 px and above",
  "Stable-release visual acceptance still required",
]);

const browserUiSources = [canonicalCss, canonicalAccessibility, themeBridge, notesFoundation];
const forbiddenRemotePatterns = [
  /@import\s+url\s*\(/i,
  /fonts\.googleapis\.com/i,
  /fonts\.gstatic\.com/i,
  /use\.fontawesome\.com/i,
  /cdnjs\.cloudflare\.com/i,
  /unpkg\.com/i,
  /cdn\.jsdelivr\.net/i,
];
for (const pattern of forbiddenRemotePatterns) {
  if (browserUiSources.some((content) => pattern.test(content))) {
    throw new Error(`Glaze browser UI must remain local and privacy-preserving; matched ${pattern}`);
  }
}

console.log(
  `Glaze UI ${EXPECTED_GLAZE_VERSION} conformance validated at canonical revision ${EXPECTED_GLAZE_REVISION}.`,
);
