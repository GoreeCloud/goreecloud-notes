import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  ApiError,
  createNote,
  documentToText,
  getCurrentUser,
  listNotes,
  login as loginRequest,
  logout as logoutRequest,
  textToDocument,
  trashNote,
  updateNote,
  type CurrentUser,
  type Note,
} from "./api";

const navigation = [
  "Home",
  "All Notes",
  "Notebooks",
  "Tags",
  "Shortcuts",
  "Archive",
  "Trash",
];

function SourceLink() {
  return (
    <a className="source-link" href="https://github.com/GoreeCloud/goreecloud-notes">
      Source code
    </a>
  );
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred.";
}

type LoginScreenProps = {
  onAuthenticated: (user: CurrentUser) => Promise<void>;
};

function LoginScreen({ onAuthenticated }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      const user = await loginRequest(username, password);
      await onAuthenticated(user);
    } catch (caught) {
      setError(messageFromError(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-heading">
        <div className="brand-row auth-brand">
          <div className="brand-mark" aria-hidden="true">G</div>
          <div>
            <strong>GoreeCloud</strong>
            <span>Notes</span>
          </div>
        </div>

        <div className="auth-copy">
          <p className="eyebrow">Private knowledge workspace</p>
          <h1 id="login-heading">Welcome back</h1>
          <p>Sign in with an account created by the GoreeCloud Notes administrator.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            <span>Username</span>
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error ? <p className="form-error" role="alert">{error}</p> : null}

          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <footer className="auth-footer">
          <span>Private by default · AGPL-3.0-only</span>
          <SourceLink />
        </footer>
      </section>
    </main>
  );
}

function App() {
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState("Saved");

  const selectedNote = notes.find((note) => note.id === selectedId) ?? null;
  const dirty = selectedNote
    ? selectedNote.title !== title || documentToText(selectedNote.document) !== body
    : false;

  const visibleNotes = useMemo(() => {
    const query = search.trim().casefold?.() ?? search.trim().toLowerCase();
    if (!query) {
      return notes;
    }

    return notes.filter((note) => {
      const haystack = `${note.title}\n${documentToText(note.document)}`.toLowerCase();
      return haystack.includes(query.toLowerCase());
    });
  }, [notes, search]);

  function openNote(note: Note | null) {
    if (note === null) {
      setSelectedId(null);
      setTitle("");
      setBody("");
      setSaveState("Saved");
      return;
    }

    setSelectedId(note.id);
    setTitle(note.title);
    setBody(documentToText(note.document));
    setSaveState("Saved");
    setError("");
  }

  async function hydrateWorkspace(authenticatedUser: CurrentUser) {
    const loadedNotes = await listNotes();
    setUser(authenticatedUser);
    setNotes(loadedNotes);
    setAuthState("authenticated");
    openNote(loadedNotes[0] ?? null);
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const currentUser = await getCurrentUser();
        const loadedNotes = await listNotes();
        if (cancelled) {
          return;
        }

        setUser(currentUser);
        setNotes(loadedNotes);
        setAuthState("authenticated");
        if (loadedNotes[0]) {
          setSelectedId(loadedNotes[0].id);
          setTitle(loadedNotes[0].title);
          setBody(documentToText(loadedNotes[0].document));
        }
      } catch (caught) {
        if (cancelled) {
          return;
        }
        if (caught instanceof ApiError && caught.status === 401) {
          setAuthState("unauthenticated");
        } else {
          setError(messageFromError(caught));
          setAuthState("unauthenticated");
        }
      }
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreateNote() {
    setBusy(true);
    setError("");
    try {
      const note = await createNote();
      setNotes((current) => [note, ...current]);
      openNote(note);
    } catch (caught) {
      setError(messageFromError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave() {
    if (!selectedNote || !dirty) {
      return;
    }

    setBusy(true);
    setError("");
    setSaveState("Saving…");
    try {
      const updated = await updateNote(selectedNote.id, {
        title,
        document: textToDocument(body),
      });
      setNotes((current) => current.map((note) => (note.id === updated.id ? updated : note)));
      setTitle(updated.title);
      setBody(documentToText(updated.document));
      setSaveState("Saved");
    } catch (caught) {
      setSaveState("Not saved");
      setError(messageFromError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleTrash() {
    if (!selectedNote) {
      return;
    }

    setBusy(true);
    setError("");
    try {
      await trashNote(selectedNote.id);
      const remaining = notes.filter((note) => note.id !== selectedNote.id);
      setNotes(remaining);
      openNote(remaining[0] ?? null);
    } catch (caught) {
      setError(messageFromError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    setError("");
    try {
      await logoutRequest();
      setUser(null);
      setNotes([]);
      openNote(null);
      setAuthState("unauthenticated");
    } catch (caught) {
      setError(messageFromError(caught));
    } finally {
      setBusy(false);
    }
  }

  if (authState === "loading") {
    return (
      <main className="loading-shell" aria-live="polite">
        <div className="brand-mark" aria-hidden="true">G</div>
        <span>Opening GoreeCloud Notes…</span>
      </main>
    );
  }

  if (authState === "unauthenticated") {
    return <LoginScreen onAuthenticated={hydrateWorkspace} />;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="GoreeCloud Notes navigation">
        <div className="brand-row">
          <div className="brand-mark" aria-hidden="true">G</div>
          <div>
            <strong>GoreeCloud</strong>
            <span>Notes</span>
          </div>
        </div>

        <button className="new-note" type="button" onClick={handleCreateNote} disabled={busy}>
          + New note
        </button>

        <nav>
          {navigation.map((item, index) => (
            <button
              className={`nav-item${index === 0 ? " active" : ""}`}
              type="button"
              key={item}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer account-footer">
          <div>
            <span className="status-dot" aria-hidden="true" />
            <span className="account-name">{user?.display_name}</span>
          </div>
          <button type="button" onClick={handleLogout} disabled={busy}>Sign out</button>
        </div>
      </aside>

      <section className="note-list-pane" aria-label="Notes">
        <header className="pane-header">
          <div>
            <p className="eyebrow">Home</p>
            <h1>Quick Notes</h1>
          </div>
          <span className="note-count">{notes.length}</span>
        </header>

        <label className="search-box">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="Search loaded notes"
            aria-label="Search notes"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <button className="quick-capture" type="button" onClick={handleCreateNote} disabled={busy}>
          <span>Take a note…</span>
          <span className="quick-actions" aria-hidden="true">＋</span>
        </button>

        {error ? <p className="workspace-error" role="alert">{error}</p> : null}

        <div className="notes-stack">
          {visibleNotes.map((note) => {
            const preview = documentToText(note.document) || "Empty note";
            return (
              <button
                className={`note-card${note.id === selectedId ? " selected" : ""}`}
                type="button"
                key={note.id}
                onClick={() => openNote(note)}
              >
                <h2>{note.title || "Untitled"}</h2>
                <p>{preview}</p>
                <small>{new Date(note.updated_at).toLocaleString()}</small>
              </button>
            );
          })}
          {visibleNotes.length === 0 ? (
            <div className="empty-list">
              <strong>{notes.length === 0 ? "No notes yet" : "No matching notes"}</strong>
              <span>{notes.length === 0 ? "Create your first private note." : "Try another search."}</span>
            </div>
          ) : null}
        </div>

        <footer className="mobile-source-footer">
          <span>AGPL-3.0-only</span>
          <span aria-hidden="true"> · </span>
          <SourceLink />
        </footer>
      </section>

      <section className="editor-pane" aria-label="Note editor">
        {selectedNote ? (
          <>
            <header className="editor-toolbar">
              <div className="crumbs">Home / Quick Notes</div>
              <div className="toolbar-actions editor-actions">
                <span className={`save-state${dirty ? " dirty" : ""}`}>{dirty ? "Unsaved changes" : saveState}</span>
                <button type="button" onClick={handleTrash} disabled={busy}>Trash</button>
                <button className="save-button" type="button" onClick={handleSave} disabled={busy || !dirty}>
                  Save
                </button>
              </div>
            </header>

            <article className="editor-surface live-editor">
              <p className="eyebrow">Private note</p>
              <input
                className="title-input"
                aria-label="Note title"
                placeholder="Untitled"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
              />
              <p className="editor-meta">
                Structured GoreeCloud document · manual save during Milestone 0
              </p>
              <textarea
                className="body-editor"
                aria-label="Note body"
                placeholder="Start writing…"
                value={body}
                onChange={(event) => setBody(event.target.value)}
              />
              <div className="callout foundation-callout">
                <strong>Native persistence is active</strong>
                <span>
                  This bridge stores the note through the user-isolated PostgreSQL API. Rich-text editing and autosave remain later gates.
                </span>
              </div>
            </article>
          </>
        ) : (
          <div className="empty-editor">
            <p className="eyebrow">GoreeCloud Notes</p>
            <h2>Your private workspace is ready.</h2>
            <p>Create a note to begin building your knowledge library.</p>
            <button className="primary-button" type="button" onClick={handleCreateNote} disabled={busy}>
              Create first note
            </button>
          </div>
        )}

        <footer className="source-footer">
          <span>AGPL-3.0-only</span>
          <span aria-hidden="true"> · </span>
          <SourceLink />
        </footer>
      </section>
    </main>
  );
}

export default App;
