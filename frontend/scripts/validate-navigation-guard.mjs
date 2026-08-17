import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src");

const guard = readFileSync(resolve(src, "WorkspaceNavigationGuard.tsx"), "utf8");
const css = readFileSync(resolve(src, "navigation-guard.css"), "utf8");
const app = readFileSync(resolve(src, "App.tsx"), "utf8");
const main = readFileSync(resolve(src, "main.tsx"), "utf8");

const failures = [];

function requireText(haystack, needle, message) {
  if (!haystack.includes(needle)) failures.push(message);
}

function forbidText(haystack, needle, message) {
  if (haystack.includes(needle)) failures.push(message);
}

requireText(main, "<WorkspaceNavigationGuard />", "Root must mount WorkspaceNavigationGuard.");
requireText(main, 'from "./WorkspaceNavigationGuard"', "main.tsx must import WorkspaceNavigationGuard.");

requireText(guard, 'window.addEventListener("beforeunload"', "Guard must protect browser close/refresh.");
requireText(guard, 'document.addEventListener("click", handleClick, true)', "Guard must intercept context-changing clicks in capture phase.");
requireText(guard, 'event.stopImmediatePropagation()', "Guard must stop the original React navigation event while a draft is protected.");
requireText(guard, 'document.querySelector<HTMLElement>(".save-state")', "Guard must derive draft state from the existing save-state contract.");
requireText(guard, 'document.querySelector<HTMLButtonElement>(".save-button")', "Guard must delegate Save & continue to the existing save action.");
requireText(guard, '"Archive", "Trash", "Restore"', "Guard must protect state-changing actions that leave the current editing context.");
requireText(guard, "Discard &amp; continue", "Guard must expose an explicit destructive discard choice.");
requireText(guard, "Save & continue", "Guard must expose Save & continue.");
requireText(guard, 'role="dialog"', "Guard must use dialog semantics.");
requireText(guard, 'aria-modal="true"', "Guard must identify the modal boundary to assistive technology.");
requireText(guard, 'setAttribute("inert", "")', "Guard must make background application controls inert while the dialog is open.");
requireText(guard, 'event.key === "Escape"', "Guard must support Escape cancellation.");
requireText(guard, 'event.key !== "Tab"', "Guard must keep keyboard focus inside the dialog.");

for (const hook of ["nav-item", "sidebar-library-item", "note-card", "new-note", "quick-capture", "account-footer", "editor-actions", "save-state", "save-button"]) {
  requireText(app, hook, `App.tsx must retain the guarded ${hook} interaction hook.`);
}

requireText(css, "var(--glaze-target-min)", "Guard controls must use the Glaze minimum target token.");
requireText(css, "var(--glaze-target-comfortable)", "Compact guard controls must use the Glaze comfortable target token.");
requireText(css, "@media (max-width: 599px)", "Guard must adapt for the Glaze Compact range.");
requireText(css, "prefers-reduced-motion: reduce", "Guard must provide reduced-motion behavior.");
requireText(css, "prefers-reduced-transparency: reduce", "Guard must provide reduced-transparency behavior.");
requireText(css, "@supports not ((backdrop-filter", "Guard must provide a solid no-backdrop-filter fallback.");
requireText(css, "prefers-contrast: more", "Guard must support increased-contrast preferences.");
requireText(css, "forced-colors: active", "Guard must remain operable in forced-colors mode.");
requireText(css, "var(--glaze-motion-emphasized)", "Dialog entrance must use the Glaze emphasized motion token.");

forbidText(guard, "window.confirm", "Do not replace the Glaze dialog with window.confirm.");
forbidText(guard, "window.alert", "Do not introduce window.alert into draft protection.");
forbidText(guard, "http://", "Draft protection must not introduce remote browser dependencies.");
forbidText(guard, "https://", "Draft protection must not introduce remote browser dependencies.");

if (failures.length > 0) {
  console.error("Navigation guard validation failed:\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log("Navigation guard validation passed.");
