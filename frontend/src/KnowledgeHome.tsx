import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  documentToText,
  getCurrentUser,
  listNotebooks,
  listNotes,
  listTags,
  type CurrentUser,
  type Note,
  type Notebook,
  type Tag,
} from "./api";

type HomeModuleId = "recent" | "pinned" | "scratch" | "shortcuts" | "tags";
type HomeModuleSize = "standard" | "wide";

type HomeModulePreference = {
  id: HomeModuleId;
  visible: boolean;
  size: HomeModuleSize;
};

type KnowledgeHomeProps = {
  onOpenWorkspace: () => void;
};

const DEFAULT_MODULES: HomeModulePreference[] = [
  { id: "recent", visible: true, size: "wide" },
  { id: "scratch", visible: true, size: "standard" },
  { id: "pinned", visible: true, size: "standard" },
  { id: "shortcuts", visible: true, size: "standard" },
  { id: "tags", visible: true, size: "standard" },
];

const MODULE_LABELS: Record<HomeModuleId, string> = {
  recent: "Recent Notes",
  pinned: "Pinned Notes",
  scratch: "Scratch Pad",
  shortcuts: "Shortcuts",
  tags: "Tags",
};

function preferenceKey(userId: string): string {
  return `goreecloud.notes.knowledge-home.v1.${userId}`;
}

function scratchKey(userId: string): string {
  return `goreecloud.notes.scratch-pad.v1.${userId}`;
}

function normalizePreferences(value: unknown): HomeModulePreference[] {
  if (!Array.isArray(value)) return DEFAULT_MODULES;

  const known = new Set<HomeModuleId>();
  const normalized: HomeModulePreference[] = [];
  for (const entry of value) {
    if (typeof entry !== "object" || entry === null) continue;
    const raw = entry as Record<string, unknown>;
    const id = raw.id as HomeModuleId;
    if (!(id in MODULE_LABELS) || known.has(id)) continue;
    known.add(id);
    normalized.push({
      id,
      visible: raw.visible !== false,
      size: raw.size === "wide" ? "wide" : "standard",
    });
  }

  for (const fallback of DEFAULT_MODULES) {
    if (!known.has(fallback.id)) normalized.push(fallback);
  }
  return normalized;
}

function readPreferences(userId: string): HomeModulePreference[] {
  try {
    const raw = window.localStorage.getItem(preferenceKey(userId));
    return raw ? normalizePreferences(JSON.parse(raw)) : DEFAULT_MODULES;
  } catch {
    return DEFAULT_MODULES;
  }
}

function writePreferences(userId: string, preferences: HomeModulePreference[]): void {
  try {
    window.localStorage.setItem(preferenceKey(userId), JSON.stringify(preferences));
  } catch {
    // Home customization is optional. A storage failure must not block access to Notes.
  }
}

function readScratch(userId: string): string {
  try {
    return window.sessionStorage.getItem(scratchKey(userId)) ?? "";
  } catch {
    return "";
  }
}

function writeScratch(userId: string, value: string): void {
  try {
    if (value) window.sessionStorage.setItem(scratchKey(userId), value);
    else window.sessionStorage.removeItem(scratchKey(userId));
  } catch {
    // Scratch Pad remains best-effort transient browser state until promoted to a Note.
  }
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}

function noteExcerpt(note: Note): string {
  const value = documentToText(note.document).trim();
  return value || "Empty note";
}

function HomeNoteCard({ note }: { note: Note }) {
  return (
    <article className="knowledge-note-card glaze-surface-solid">
      <div className="knowledge-note-card-heading">
        <h3>{note.title || "Untitled"}</h3>
        {note.is_pinned ? <span className="knowledge-pin" aria-label="Pinned">Pinned</span> : null}
      </div>
      <p>{noteExcerpt(note)}</p>
      <time dateTime={note.updated_at}>{new Date(note.updated_at).toLocaleString()}</time>
    </article>
  );
}

export function KnowledgeHome({ onOpenWorkspace }: KnowledgeHomeProps) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [archivedCount, setArchivedCount] = useState(0);
  const [trashedCount, setTrashedCount] = useState(0);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [preferences, setPreferences] = useState<HomeModulePreference[]>(DEFAULT_MODULES);
  const [scratch, setScratch] = useState("");
  const [customizing, setCustomizing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [currentUser, normalNotes, archivedNotes, trashedNotes, loadedNotebooks, loadedTags] = await Promise.all([
          getCurrentUser(),
          listNotes({ state: "normal" }),
          listNotes({ state: "archived" }),
          listNotes({ state: "trashed" }),
          listNotebooks(),
          listTags(),
        ]);
        if (cancelled) return;
        setUser(currentUser);
        setNotes(normalNotes);
        setArchivedCount(archivedNotes.length);
        setTrashedCount(trashedNotes.length);
        setNotebooks(loadedNotebooks);
        setTags(loadedTags);
        setPreferences(readPreferences(currentUser.id));
        setScratch(readScratch(currentUser.id));
      } catch (caught) {
        if (!cancelled) setError(messageFromError(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const recentNotes = useMemo(
    () => [...notes].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at)).slice(0, 6),
    [notes],
  );
  const pinnedNotes = useMemo(() => notes.filter((note) => note.is_pinned).slice(0, 4), [notes]);
  const visibleModules = preferences.filter((item) => item.visible);

  function commitPreferences(next: HomeModulePreference[]) {
    setPreferences(next);
    if (user) writePreferences(user.id, next);
  }

  function toggleVisibility(id: HomeModuleId) {
    commitPreferences(preferences.map((item) => item.id === id ? { ...item, visible: !item.visible } : item));
  }

  function toggleSize(id: HomeModuleId) {
    commitPreferences(preferences.map((item) => item.id === id ? { ...item, size: item.size === "wide" ? "standard" : "wide" } : item));
  }

  function moveModule(id: HomeModuleId, direction: -1 | 1) {
    const index = preferences.findIndex((item) => item.id === id);
    const nextIndex = index + direction;
    if (index < 0 || nextIndex < 0 || nextIndex >= preferences.length) return;
    const next = [...preferences];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    commitPreferences(next);
  }

  function updateScratch(value: string) {
    setScratch(value);
    if (user) writeScratch(user.id, value);
  }

  function renderModule(item: HomeModulePreference) {
    const moduleClass = `knowledge-module glaze-panel glaze-surface-solid${item.size === "wide" ? " knowledge-module-wide" : ""}`;

    if (item.id === "recent") {
      return (
        <section className={moduleClass} key={item.id} aria-labelledby="knowledge-recent-heading">
          <header className="knowledge-module-header"><div><span className="knowledge-kicker">Library</span><h2 id="knowledge-recent-heading">Recent Notes</h2></div><button className="knowledge-text-action" type="button" onClick={onOpenWorkspace}>Open workspace</button></header>
          <div className="knowledge-note-grid">{recentNotes.map((note) => <HomeNoteCard key={note.id} note={note} />)}{recentNotes.length === 0 ? <p className="knowledge-empty">No current notes yet.</p> : null}</div>
        </section>
      );
    }

    if (item.id === "pinned") {
      return (
        <section className={moduleClass} key={item.id} aria-labelledby="knowledge-pinned-heading">
          <header className="knowledge-module-header"><div><span className="knowledge-kicker">Focus</span><h2 id="knowledge-pinned-heading">Pinned Notes</h2></div></header>
          <div className="knowledge-note-grid knowledge-note-grid-compact">{pinnedNotes.map((note) => <HomeNoteCard key={note.id} note={note} />)}{pinnedNotes.length === 0 ? <p className="knowledge-empty">Pin important notes in the workspace to surface them here.</p> : null}</div>
        </section>
      );
    }

    if (item.id === "scratch") {
      return (
        <section className={moduleClass} key={item.id} aria-labelledby="knowledge-scratch-heading">
          <header className="knowledge-module-header"><div><span className="knowledge-kicker">Transient capture</span><h2 id="knowledge-scratch-heading">Scratch Pad</h2></div><span className="knowledge-private-badge">This tab</span></header>
          <textarea className="knowledge-scratch" value={scratch} maxLength={4000} placeholder="Capture a thought without creating a note yet…" aria-label="Scratch Pad" onChange={(event) => updateScratch(event.target.value)} />
          <div className="knowledge-scratch-footer"><span>{scratch.length.toLocaleString()} / 4,000</span><button className="knowledge-text-action" type="button" onClick={() => updateScratch("")} disabled={!scratch}>Clear</button></div>
          <p className="knowledge-module-note">Scratch Pad is session-scoped transient text, not a hidden note store. Promotion into a normal Note remains a separately gated follow-up.</p>
        </section>
      );
    }

    if (item.id === "shortcuts") {
      return (
        <section className={moduleClass} key={item.id} aria-labelledby="knowledge-shortcuts-heading">
          <header className="knowledge-module-header"><div><span className="knowledge-kicker">Navigate</span><h2 id="knowledge-shortcuts-heading">Shortcuts</h2></div></header>
          <div className="knowledge-shortcuts">
            <button type="button" onClick={onOpenWorkspace}><strong>{notes.length}</strong><span>Current notes</span></button>
            <button type="button" onClick={onOpenWorkspace}><strong>{notebooks.length}</strong><span>Notebooks</span></button>
            <button type="button" onClick={onOpenWorkspace}><strong>{archivedCount}</strong><span>Archived</span></button>
            <button type="button" onClick={onOpenWorkspace}><strong>{trashedCount}</strong><span>Trash</span></button>
          </div>
        </section>
      );
    }

    return (
      <section className={moduleClass} key={item.id} aria-labelledby="knowledge-tags-heading">
        <header className="knowledge-module-header"><div><span className="knowledge-kicker">Organize</span><h2 id="knowledge-tags-heading">Tags</h2></div><button className="knowledge-text-action" type="button" onClick={onOpenWorkspace}>Manage</button></header>
        <div className="knowledge-tag-cloud">{tags.slice(0, 16).map((tag) => <span key={tag.id} className="knowledge-tag"><span className="knowledge-tag-dot" aria-hidden="true" style={{ backgroundColor: tag.color ?? undefined }} />{tag.name}</span>)}{tags.length === 0 ? <p className="knowledge-empty">No tags yet.</p> : null}</div>
      </section>
    );
  }

  if (loading) {
    return <main className="knowledge-home-shell"><div className="knowledge-home-loading" aria-live="polite">Opening Knowledge Home…</div></main>;
  }

  if (!user || error) {
    return (
      <main className="knowledge-home-shell">
        <section className="knowledge-home-state glaze-panel glaze-surface-solid" aria-labelledby="knowledge-home-unavailable">
          <span className="knowledge-kicker">GoreeCloud Notes</span>
          <h1 id="knowledge-home-unavailable">Knowledge Home needs an active Notes session.</h1>
          <p>{error || "Sign in through the Notes workspace, then open Knowledge Home again."}</p>
          <button className="glaze-button" data-variant="primary" type="button" onClick={onOpenWorkspace}>Open Notes workspace</button>
        </section>
      </main>
    );
  }

  return (
    <main className="knowledge-home-shell">
      <header className="knowledge-home-topbar glaze-overlay">
        <div className="knowledge-home-brand"><span className="knowledge-home-mark" aria-hidden="true">G</span><div><strong>GoreeCloud Notes</strong><span>Knowledge Home</span></div></div>
        <div className="knowledge-home-actions"><button className="glaze-button" type="button" aria-expanded={customizing} onClick={() => setCustomizing((current) => !current)}>{customizing ? "Done" : "Customize"}</button><button className="glaze-button" data-variant="primary" type="button" onClick={onOpenWorkspace}>Open Notes</button></div>
      </header>

      <section className="knowledge-home-heading">
        <div><p className="knowledge-kicker">Private knowledge workspace</p><h1>{user.display_name ? `${user.display_name}’s Home` : "Your Knowledge Home"}</h1><p>Recent work and owned Notes context, composed as a native GoreeCloud home rather than a duplicate task, calendar, or recommendation system.</p></div>
        <div className="knowledge-home-summary" aria-label="Library summary"><span><strong>{notes.length}</strong> current notes</span><span><strong>{notebooks.length}</strong> notebooks</span><span><strong>{tags.length}</strong> tags</span></div>
      </section>

      {customizing ? (
        <section className="knowledge-customizer glaze-panel glaze-surface-solid" aria-labelledby="knowledge-customize-heading">
          <header><div><span className="knowledge-kicker">Local presentation preference</span><h2 id="knowledge-customize-heading">Customize Home</h2></div><button type="button" className="knowledge-text-action" onClick={() => commitPreferences(DEFAULT_MODULES)}>Reset</button></header>
          <p>Visibility, order, and supported module width are stored only as a browser presentation preference for this account.</p>
          <div className="knowledge-customizer-list">
            {preferences.map((item, index) => (
              <div className="knowledge-customizer-row" key={item.id}>
                <strong>{MODULE_LABELS[item.id]}</strong>
                <div>
                  <button type="button" onClick={() => moveModule(item.id, -1)} disabled={index === 0} aria-label={`Move ${MODULE_LABELS[item.id]} earlier`}>↑</button>
                  <button type="button" onClick={() => moveModule(item.id, 1)} disabled={index === preferences.length - 1} aria-label={`Move ${MODULE_LABELS[item.id]} later`}>↓</button>
                  <button type="button" onClick={() => toggleSize(item.id)}>{item.size === "wide" ? "Standard width" : "Wide"}</button>
                  <button type="button" onClick={() => toggleVisibility(item.id)} aria-pressed={item.visible}>{item.visible ? "Shown" : "Hidden"}</button>
                </div>
              </div>
            ))}
          </div>
          <p className="knowledge-module-note">Suggested/Relevant Notes are withheld until deterministic ranking is approved. Recently Captured is withheld until capture provenance is connected. GoreeCloud Tasks and Calendar modules are withheld until their authoritative capabilities are discoverable through GoreeCloud Mesh.</p>
        </section>
      ) : null}

      <div className="knowledge-home-grid">{visibleModules.map(renderModule)}{visibleModules.length === 0 ? <section className="knowledge-home-state glaze-panel glaze-surface-solid"><h2>Your Home is clear.</h2><p>Use Customize to show a module again.</p></section> : null}</div>

      <footer className="knowledge-home-footer"><span>First-party GoreeCloud Notes · private session data only</span><button type="button" onClick={onOpenWorkspace}>Return to Notes workspace</button></footer>
    </main>
  );
}
