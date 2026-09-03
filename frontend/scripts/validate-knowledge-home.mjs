import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../src");

const home = readFileSync(resolve(src, "KnowledgeHome.tsx"), "utf8");
const api = readFileSync(resolve(src, "api.ts"), "utf8");
const css = readFileSync(resolve(src, "knowledge-home.css"), "utf8");
const main = readFileSync(resolve(src, "main.tsx"), "utf8");

const failures = [];

function requireText(haystack, needle, message) {
  if (!haystack.includes(needle)) failures.push(message);
}

function forbidText(haystack, needle, message) {
  if (haystack.includes(needle)) failures.push(message);
}

for (const label of ["Recent Notes", "Relevant Notes", "Pinned Notes", "Scratch Pad", "Shortcuts", "Tags"]) {
  requireText(home, label, `Knowledge Home must retain the ${label} module.`);
}

requireText(home, 'window.localStorage.setItem(preferenceKey(userId)', "Home presentation preferences must remain local browser state.");
requireText(home, 'window.sessionStorage.setItem(scratchKey(userId)', "Scratch Pad must remain session-scoped transient browser state.");
requireText(home, 'window.sessionStorage.removeItem(scratchKey(userId))', "Scratch Pad must have an explicit transient-storage removal path.");
requireText(home, "function writeScratch(userId: string, value: string): boolean", "Scratch Pad storage writes must report whether transient persistence operations succeeded.");
requireText(home, "Scratch Pad is session-scoped transient text, not a hidden note store.", "Scratch Pad must state its non-authoritative persistence boundary.");
requireText(home, "Save as note", "Scratch Pad must expose explicit promotion into a normal Note.");
requireText(home, "createNote,", "Knowledge Home must use the established Notes API boundary for Scratch Pad promotion.");
requireText(home, "textToDocument,", "Scratch Pad promotion must use the GoreeCloud document contract converter.");
requireText(home, "async function handleSaveScratchAsNote()", "Scratch Pad promotion must use a dedicated async save boundary.");
requireText(home, "const created = await createNote(null, {", "Scratch Pad promotion must create the populated note in one owner-authorized request.");
requireText(home, "document: textToDocument(source)", "Scratch Pad promotion must convert transient text through the native document contract.");
requireText(home, "setNotes((current) => [created", "Successful Scratch Pad promotion must immediately refresh Home's native note state.");
requireText(home, 'const scratchCleared = writeScratch(user.id, "");', "Scratch Pad promotion must verify transient-storage removal after durable creation.");
requireText(home, "if (scratchCleared)", "Scratch Pad UI text must remain visible when transient-storage removal fails.");
requireText(home, "could not clear its transient Scratch Pad copy", "Successful durable promotion with failed transient cleanup must be disclosed.");
requireText(home, "Could not save Scratch Pad:", "Failed Scratch Pad promotion must surface an explicit error while leaving transient text available.");
requireText(home, "function handleClearScratch()", "Manual Scratch Pad clearing must use a recoverable storage-aware path.");
requireText(home, "The captured text remains visible so you can retry.", "Manual clear failure must preserve visible transient text.");
requireText(home, "disabled={scratchSaving}", "Scratch Pad editing must pause while durable promotion is in flight.");
requireText(home, "the transient copy is cleared when this tab’s session storage accepts the removal.", "Scratch Pad must truthfully disclose transient cleanup behavior.");

const scratchSaveStart = home.indexOf("async function handleSaveScratchAsNote()");
const scratchCreate = home.indexOf("const created = await createNote(null, {", scratchSaveStart);
const scratchClearAttempt = home.indexOf('const scratchCleared = writeScratch(user.id, "");', scratchCreate);
const scratchUiClear = home.indexOf('setScratch("");', scratchClearAttempt);
if (
  scratchSaveStart < 0
  || scratchCreate < scratchSaveStart
  || scratchClearAttempt < scratchCreate
  || scratchUiClear < scratchClearAttempt
) {
  failures.push("Scratch Pad transient state must be cleared only after the durable note create call succeeds and browser storage confirms removal.");
}

requireText(api, "export type NoteCreateContent = {", "The Notes client API must define bounded initial content for atomic note creation.");
requireText(api, "initial: NoteCreateContent = {}", "Existing createNote callers must remain backward-compatible while initial content is supported.");
requireText(api, 'const document = initial.document ?? emptyDocument();', "Normal empty-note creation must remain the default behavior.");
requireText(api, "JSON.stringify({ title, document, notebook_id: notebookId })", "Populated note creation must remain one CSRF-protected native API request.");

requireText(home, "function relevanceScore(note: Note): number", "Relevant Notes must use an explicit deterministic local ranking function.");
requireText(home, "note.is_pinned ? 3 : 0", "Relevant Notes ranking must retain the documented native pin-state contribution.");
requireText(home, "bodyLength >= 240 ? 1 : 0", "Relevant Notes ranking must retain the documented bounded note-substance contribution.");
requireText(home, "Date.parse(right.updated_at) - Date.parse(left.updated_at)", "Relevant Notes must use native update order as a deterministic tie-break.");
requireText(home, "left.id.localeCompare(right.id)", "Relevant Notes must use a stable ID tie-break rather than nondeterministic ordering.");
requireText(home, "No behavioral tracking, remote recommendation service, or AI inference is used.", "Relevant Notes must disclose its local non-behavioral non-AI boundary.");
requireText(home, "Relevant Notes uses a transparent local deterministic ranking over already authorized Notes data.", "Home customization must disclose the Relevant Notes data-authority boundary.");
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
requireText(css, ".knowledge-scratch-actions .glaze-button", "Scratch Pad durable-save controls must use covered 48px targets.");
requireText(css, ".knowledge-scratch-status", "Scratch Pad promotion must have visible success/error status styling.");
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
forbidText(home, "localStorage.setItem(\"goreecloud.notes.relevance", "Relevant Notes must not introduce behavioral or derived-ranking persistence.");

if (failures.length > 0) {
  console.error("Knowledge Home validation failed:\n" + failures.map((failure) => `- ${failure}`).join("\n"));
  process.exit(1);
}

console.log("Knowledge Home validation passed.");