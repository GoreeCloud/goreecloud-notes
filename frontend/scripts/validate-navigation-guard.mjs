import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src");

const guard = readFileSync(resolve(src, "WorkspaceNavigationGuard.tsx"), "utf8");
const css = readFileSync(resolve(src, "navigation-guard.css"), "utf8");
const app = readFileSync(resolve(src, "App.tsx"), "utf8");
const main = readFileSync(resolve(src, "main.tsx"), "utf8");
const richEditor = readFileSync(resolve(src, "RichNoteEditorCore.tsx"), "utf8");
const richEditorBoundary = readFileSync(resolve(src, "RichNoteEditor.tsx"), "utf8");
const noteLinksCss = readFileSync(resolve(src, "note-links.css"), "utf8");

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
requireText(guard, '".note-link-open"', "Guard must intercept Connected-note and inline-note navigation.");
requireText(guard, 'target.getAttribute("aria-disabled") === "true"', "Guard must ignore temporarily disabled non-button navigation affordances.");
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

requireText(app, "async function handleOpenLinkedNote(noteId: string)", "App must own linked-note navigation state changes.");
requireText(app, "const target = await getNote(noteId);", "Linked-note navigation must resolve the target through the authenticated note API.");
requireText(app, 'target.state === "archived" ? "archive" : target.state === "trashed" ? "trash" : "home"', "Linked-note navigation must move to the target lifecycle view.");
requireText(app, "const loaded = await listNotes({ state: target.state });", "Linked-note navigation must rebuild the canonical lifecycle list.");
requireText(app, "onOpenNote={(noteId) => void handleOpenLinkedNote(noteId)}", "App must connect the rich editor to its linked-note opener.");
requireText(app, 'navigationDisabled={busy && saveState !== "Saving…"}', "App must prevent unrelated busy operations from racing relationship navigation while keeping active-save interception possible.");

requireText(richEditorBoundary, "onOpenNote: (noteId: string) => void;", "Lazy rich-editor boundary must carry linked-note navigation.");
requireText(richEditorBoundary, "navigationDisabled?: boolean;", "Lazy rich-editor boundary must carry navigation availability separately from editor editability.");
requireText(richEditor, 'className="note-link-chip note-link-open"', "Connected notes must render as guarded navigation buttons.");
requireText(richEditor, 'aria-label={`Open ${label}`}', "Connected-note buttons must expose a descriptive accessible name.");
requireText(richEditor, "onClick={() => onOpenNote(note.id)}", "Connected-note buttons must open the resolved note by ID.");
requireText(richEditor, "relationships.outgoing.map((note) => <ConnectedNoteButton", "Outgoing relationships must be navigable.");
requireText(richEditor, "relationships.backlinks.map((note) => <ConnectedNoteButton", "Backlinks must be navigable.");
requireText(richEditor, "const relationshipNavigationDisabled = navigationDisabled || linksLoading;", "Relationship navigation must be disabled only for unrelated busy state or relationship refresh.");

requireText(richEditor, 'class: "goree-note-link note-link-open"', "Inline noteLink marks must participate in the guarded navigation hook.");
requireText(richEditor, 'role: "link"', "Inline noteLink marks must expose link semantics.");
requireText(richEditor, 'tabindex: "0"', "Inline noteLink marks must be keyboard focusable.");
requireText(richEditor, 'title: "Open linked note"', "Inline noteLink marks must disclose their navigation behavior.");
requireText(richEditor, "const UUID_PATTERN =", "Inline navigation must fail closed on malformed note references.");
requireText(richEditor, "function openInlineNoteLink(element: HTMLElement)", "Inline note navigation must use a dedicated validation boundary.");
requireText(richEditor, "navigationDisabledRef.current", "Inline note navigation must honor unrelated busy-state disablement.");
requireText(richEditor, "currentNoteIdRef.current", "Inline note navigation must refuse self-navigation.");
requireText(richEditor, "onOpenNoteRef.current(targetNoteId)", "Inline note navigation must reuse the App-owned authenticated opener.");
requireText(richEditor, "handleClick: (_view, _position, event) =>", "Inline note marks must support direct primary-pointer activation.");
requireText(richEditor, 'event.target.closest<HTMLElement>(".goree-note-link.note-link-open[data-note-id]")', "Inline navigation must resolve only the local noteLink mark element.");
requireText(richEditor, "handleKeyDown: (_view, event) =>", "Inline note marks must expose keyboard activation.");
requireText(richEditor, 'event.key !== "Enter"', "Inline note marks must use Enter as the keyboard activation key.");
requireText(richEditor, "element.click();", "Keyboard activation must replay through the same guarded click path.");
requireText(richEditor, 'element.setAttribute("aria-disabled", "true")', "Inline marks must expose temporary navigation disablement to assistive technology.");

requireText(css, "var(--glaze-target-min)", "Guard controls must use the Glaze minimum target token.");
requireText(css, "var(--glaze-target-comfortable)", "Compact guard controls must use the Glaze comfortable target token.");
requireText(css, "@media (max-width: 599px)", "Guard must adapt for the Glaze Compact range.");
requireText(css, "prefers-reduced-motion: reduce", "Guard must provide reduced-motion behavior.");
requireText(css, "prefers-reduced-transparency: reduce", "Guard must provide reduced-transparency behavior.");
requireText(css, "@supports not ((backdrop-filter", "Guard must provide a solid no-backdrop-filter fallback.");
requireText(css, "prefers-contrast: more", "Guard must support increased-contrast preferences.");
requireText(css, "forced-colors: active", "Guard must remain operable in forced-colors mode.");
requireText(css, "var(--glaze-motion-emphasized)", "Dialog entrance must use the Glaze emphasized motion token.");

requireText(noteLinksCss, "min-height: var(--glaze-target-min)", "Connected-note buttons must use the Glaze minimum target token.");
requireText(noteLinksCss, "@media (pointer: coarse)", "Connected-note and inline-note affordances must adapt for coarse pointers.");
requireText(noteLinksCss, "var(--glaze-target-comfortable)", "Connected-note buttons must use the comfortable target on coarse pointers.");
requireText(noteLinksCss, "button.note-link-chip:focus-visible", "Connected-note buttons must preserve visible keyboard focus.");
requireText(noteLinksCss, ".goree-note-link.note-link-open:focus-visible", "Inline note links must preserve visible keyboard focus.");
requireText(noteLinksCss, '.goree-note-link.note-link-open[aria-disabled="true"]', "Inline note links must visibly expose temporary disablement.");
requireText(noteLinksCss, "prefers-reduced-transparency: reduce", "Inline note-link treatment must retain a reduced-transparency fallback.");
requireText(noteLinksCss, "forced-colors: active", "Connected-note and inline-note navigation must remain operable in forced-colors mode.");

forbidText(guard, "window.confirm", "Do not replace the Glaze dialog with window.confirm.");
forbidText(guard, "window.alert", "Do not introduce window.alert into draft protection.");
forbidText(guard, "http://", "Draft protection must not introduce remote browser dependencies.");
forbidText(guard, "https://", "Draft protection must not introduce remote browser dependencies.");
forbidText(richEditor, "window.location", "Linked-note navigation must stay inside the application state model.");
forbidText(richEditor, "href=", "Internal noteLink marks must not become generic browser URLs.");

if (failures.length > 0) {
  console.error("Navigation guard validation failed:\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log("Navigation guard validation passed.");
