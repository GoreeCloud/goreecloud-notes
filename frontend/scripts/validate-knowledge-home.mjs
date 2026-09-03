import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src");

const home = readFileSync(resolve(src, "KnowledgeHome.tsx"), "utf8");
const css = readFileSync(resolve(src, "knowledge-home.css"), "utf8");
const main = readFileSync(resolve(src, "main.tsx"), "utf8");

const failures = [];

function requireText(haystack, needle, message) {
  if (!haystack.includes(needle)) failures.push(message);
}

function forbidText(haystack, needle, message) {
  if (haystack.includes(needle)) failures.push(message);
}

for (const label of ["Recent Notes", "Pinned Notes", "Scratch Pad", "Shortcuts", "Tags"]) {
  requireText(home, label, `Knowledge Home must retain the ${label} module.`);
}

requireText(home, 'window.localStorage.setItem(preferenceKey(userId)', "Home presentation preferences must remain local browser state.");
requireText(home, 'window.sessionStorage.setItem(scratchKey(userId)', "Scratch Pad must remain session-scoped transient browser state.");
requireText(home, "Scratch Pad is session-scoped transient text, not a hidden note store.", "Scratch Pad must state its non-authoritative persistence boundary.");
requireText(home, "Suggested/Relevant Notes are withheld until deterministic ranking is approved.", "Home must not fabricate recommendation behavior.");
requireText(home, "Recently Captured is withheld until capture provenance is connected.", "Home must not fabricate capture provenance.");
requireText(home, "GoreeCloud Tasks and Calendar modules are withheld until their authoritative capabilities are discoverable through GoreeCloud Mesh.", "Home must not duplicate Tasks or Calendar authority before Mesh capability discovery.");
requireText(home, 'typeof raw.id !== "string"', "Stored customization parsing must fail safely for malformed module identifiers.");
requireText(home, 'listNotes({ state: "archived" })', "Home must derive Archive summary from the existing owner-scoped Notes API.");
requireText(home, 'listNotes({ state: "trashed" })', "Home must derive Trash summary from the existing owner-scoped Notes API.");
requireText(home, "glaze-surface-solid", "Knowledge Home content modules must use solid content surfaces.");

requireText(main, 'hash === "#knowledge-home"', "Root must expose the Knowledge Home route.");
requireText(main, 'target="_blank"', "Knowledge Home launcher must preserve the current Notes tab while explicit Save remains authoritative.");
requireText(main, "Open Knowledge Home in a new tab so the current Notes draft remains open", "Knowledge Home launcher must document draft-preservation behavior.");
requireText(main, 'from "./KnowledgeHome"', "Root must import the native Knowledge Home component.");
requireText(main, 'import "./knowledge-home.css"', "Root must load Knowledge Home styling.");

requireText(css, "min-height: 48px", "Covered Knowledge Home controls must meet the current 48px minimum target requirement.");
requireText(css, "env(safe-area-inset-top)", "Compact Knowledge Home must account for device safe areas.");
requireText(css, "prefers-reduced-motion: reduce", "Knowledge Home must support reduced motion.");
requireText(css, "prefers-reduced-transparency: reduce", "Knowledge Home must support reduced transparency.");
requireText(css, "@supports not ((backdrop-filter", "Knowledge Home must provide a solid no-backdrop-filter fallback.");
requireText(css, "forced-colors: active", "Knowledge Home must remain operable in forced-colors mode.");
requireText(css, ".knowledge-module-wide", "Knowledge Home must support approved module sizing.");

forbidText(home, "fetch(\"http", "Knowledge Home must not introduce remote data dependencies.");
forbidText(home, "https://", "Knowledge Home must not introduce remote service or asset dependencies.");
forbidText(home, "OpenAI", "Knowledge Home must not imply an unimplemented AI dependency.");
forbidText(home, "Gemini", "Knowledge Home must not imply an unimplemented AI dependency.");

if (failures.length > 0) {
  console.error("Knowledge Home validation failed:\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log("Knowledge Home validation passed.");
