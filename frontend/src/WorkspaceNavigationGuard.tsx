import { useEffect, useRef, useState } from "react";

import "./navigation-guard.css";

type PendingNavigation = {
  target: HTMLElement;
  label: string;
};

type SaveResolution = "saved" | "conflict" | "error" | "timeout";

const NAVIGATION_SELECTOR = [
  ".nav-item",
  ".sidebar-library-item",
  ".note-card",
  ".new-note",
  ".quick-capture",
  ".account-footer > button",
].join(", ");

const CONTEXT_CHANGING_EDITOR_ACTIONS = new Set(["Archive", "Trash", "Restore"]);

function draftState(): "clean" | "dirty" | "saving" | "conflict" | "error" {
  const indicator = document.querySelector<HTMLElement>(".save-state");
  if (!indicator) return "clean";

  const text = indicator.textContent?.trim() ?? "";
  if (text === "Conflict") return "conflict";
  if (text === "Saving…") return "saving";
  if (text === "Not saved") return "error";
  if (indicator.classList.contains("dirty")) return "dirty";
  return "clean";
}

function draftAtRisk(): boolean {
  const state = draftState();
  return state === "dirty" || state === "saving" || state === "conflict" || state === "error";
}

function navigationTargetFromEvent(event: MouseEvent): HTMLElement | null {
  const element = event.target instanceof Element ? event.target : null;
  if (!element || element.closest(".navigation-guard-dialog")) return null;

  const directTarget = element.closest<HTMLElement>(NAVIGATION_SELECTOR);
  if (directTarget) return directTarget;

  const editorAction = element.closest<HTMLButtonElement>(".editor-actions button");
  if (!editorAction) return null;

  const label = editorAction.textContent?.trim() ?? "";
  return CONTEXT_CHANGING_EDITOR_ACTIONS.has(label) ? editorAction : null;
}

function navigationLabel(target: HTMLElement): string {
  const explicit = target.getAttribute("aria-label") ?? target.getAttribute("title");
  const text = target.textContent?.replace(/\s+/g, " ").trim();
  return explicit?.trim() || text || "the selected destination";
}

function waitForSaveResolution(timeoutMs = 15000): Promise<SaveResolution> {
  return new Promise((resolve) => {
    let settled = false;

    const finish = (resolution: SaveResolution) => {
      if (settled) return;
      settled = true;
      observer.disconnect();
      window.clearTimeout(timeout);
      resolve(resolution);
    };

    const inspect = () => {
      const state = draftState();
      if (state === "clean") finish("saved");
      else if (state === "conflict") finish("conflict");
      else if (state === "error") finish("error");
    };

    const observer = new MutationObserver(inspect);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    const timeout = window.setTimeout(() => finish("timeout"), timeoutMs);
    window.setTimeout(inspect, 0);
  });
}

export function WorkspaceNavigationGuard() {
  const [pending, setPending] = useState<PendingNavigation | null>(null);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const bypassTarget = useRef<HTMLElement | null>(null);
  const priorFocus = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      if (!draftAtRisk()) return;
      event.preventDefault();
      event.returnValue = "";
    }

    function handleClick(event: MouseEvent) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const target = navigationTargetFromEvent(event);
      if (!target || target.matches(":disabled")) return;

      if (bypassTarget.current === target) {
        bypassTarget.current = null;
        return;
      }

      if (!draftAtRisk()) return;

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      setStatus("");
      setSaving(false);
      setPending({ target, label: navigationLabel(target) });
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("click", handleClick, true);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleClick, true);
    };
  }, []);

  useEffect(() => {
    if (!pending) return;

    priorFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const inertTargets = Array.from(document.querySelectorAll<HTMLElement>(".app-shell, .glaze-utility-dock"));
    inertTargets.forEach((element) => element.setAttribute("inert", ""));
    cancelRef.current?.focus();

    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === "Escape" && !saving) {
        event.preventDefault();
        setPending(null);
        setStatus("");
        return;
      }

      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>("button:not(:disabled)"));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleDialogKeys, true);
    return () => {
      document.removeEventListener("keydown", handleDialogKeys, true);
      inertTargets.forEach((element) => element.removeAttribute("inert"));
      priorFocus.current?.focus();
    };
  }, [pending, saving]);

  function continueNavigation(target: HTMLElement) {
    if (!target.isConnected) {
      setStatus("The destination changed while the draft was being handled. Close this dialog and choose the destination again.");
      return;
    }

    bypassTarget.current = target;
    setStatus("");
    setSaving(false);
    setPending(null);
    window.setTimeout(() => target.click(), 0);
  }

  async function saveAndContinue() {
    if (!pending || saving) return;
    if (draftState() === "conflict") {
      setStatus("This draft is in conflict. Reload the server version or explicitly discard the local draft before navigating.");
      return;
    }

    const saveButton = document.querySelector<HTMLButtonElement>(".save-button");
    if (!saveButton || saveButton.disabled) {
      setStatus("Save is not currently available. Cancel and resolve the note state, or explicitly discard the local draft.");
      return;
    }

    setSaving(true);
    setStatus("Saving the current note before navigation…");
    saveButton.click();
    const resolution = await waitForSaveResolution();

    if (resolution === "saved") {
      continueNavigation(pending.target);
      return;
    }

    setSaving(false);
    if (resolution === "conflict") {
      setStatus("The save found a newer server version. The local draft was not overwritten; resolve the conflict before navigating or explicitly discard it.");
    } else if (resolution === "error") {
      setStatus("The note could not be saved. The draft is still open and navigation remains blocked.");
    } else {
      setStatus("Saving has not completed yet. The draft remains protected; try again after the current save finishes.");
    }
  }

  function discardAndContinue() {
    if (!pending || saving) return;
    continueNavigation(pending.target);
  }

  function cancelNavigation() {
    if (saving) return;
    setStatus("");
    setPending(null);
  }

  if (!pending) return null;

  const conflict = draftState() === "conflict";

  return (
    <div className="navigation-guard-backdrop" data-navigation-guard-backdrop>
      <div
        ref={dialogRef}
        className="navigation-guard-dialog glaze-overlay"
        data-navigation-guard-dialog
        role="dialog"
        aria-modal="true"
        aria-labelledby="navigation-guard-title"
        aria-describedby="navigation-guard-description"
      >
        <div className="navigation-guard-heading">
          <p className="eyebrow">Draft protection</p>
          <h2 id="navigation-guard-title">Keep your unsaved note?</h2>
        </div>
        <p id="navigation-guard-description">
          You are about to open {pending.label}. The current note has local changes that have not been safely committed to the server.
        </p>
        {conflict ? (
          <p className="navigation-guard-warning" role="status">
            A newer server version exists. Saving is disabled until the conflict is resolved.
          </p>
        ) : null}
        {status ? <p className="navigation-guard-status" role="status" aria-live="polite">{status}</p> : null}
        <div className="navigation-guard-actions">
          <button ref={cancelRef} className="glaze-button" type="button" onClick={cancelNavigation} disabled={saving}>Cancel</button>
          <button className="glaze-button" data-variant="danger" type="button" onClick={discardAndContinue} disabled={saving}>Discard &amp; continue</button>
          <button className="glaze-button" data-variant="primary" type="button" onClick={() => void saveAndContinue()} disabled={saving || conflict}>
            {saving ? "Saving…" : "Save & continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
