import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from "react";

import {
  ApiError,
  assignNoteTag,
  attachmentDownloadUrl,
  createNotebook,
  createNote,
  createTag,
  deleteAttachment,
  deleteNotebook,
  deleteTag,
  documentToText,
  getCurrentUser,
  getNote,
  listAttachments,
  listNotebooks,
  listNoteRevisions,
  listNotes,
  listNoteTags,
  listTags,
  login as loginRequest,
  logout as logoutRequest,
  removeNoteTag,
  restoreNoteRevision,
  searchNotes,
  trashNote,
  updateNote,
  uploadAttachment,
  type Attachment,
  type CurrentUser,
  type Note,
  type Notebook,
  type NoteRevision,
  type NoteState,
  type Tag,
} from "./api";
import { documentsEqual, emptyDocument, type NoteDocument } from "./document";
import { RichNoteEditor } from "./RichNoteEditor";

type WorkspaceView = "home" | "notebook" | "tag" | "archive" | "trash" | "notebooks" | "tags";
type SaveState = "Saved" | "Saving…" | "Not saved" | "Conflict";

function SourceLink() {
  return <a className="source-link" href="https://github.com/GoreeCloud/goreecloud-notes">Source code</a>;
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

type LoginScreenProps = { onAuthenticated: (user: CurrentUser) => Promise<void> };

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
        <div className="brand-row auth-brand"><div className="brand-mark" aria-hidden="true">G</div><div><strong>GoreeCloud</strong><span>Notes</span></div></div>
        <div className="auth-copy"><p className="eyebrow">Private knowledge workspace</p><h1 id="login-heading">Welcome back</h1><p>Sign in with an account created by the GoreeCloud Notes administrator.</p></div>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label><span>Username</span><input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
          <label><span>Password</span><input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Sign in"}</button>
        </form>
        <footer className="auth-footer"><span>Private by default · AGPL-3.0-only</span><SourceLink /></footer>
      </section>
    </main>
  );
}

function App() {
  const [authState, setAuthState] = useState<"loading" | "authenticated" | "unauthenticated">("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [activeNoteTags, setActiveNoteTags] = useState<Tag[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [revisions, setRevisions] = useState<NoteRevision[]>([]);
  const [view, setView] = useState<WorkspaceView>("home");
  const [filterId, setFilterId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [editorDocument, setEditorDocument] = useState<NoteDocument>(() => emptyDocument());
  const [editorNotebookId, setEditorNotebookId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<Note[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [error, setError] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("Saved");
  const [newNotebookName, setNewNotebookName] = useState("");
  const [newNotebookParent, setNewNotebookParent] = useState("");
  const [newTagName, setNewTagName] = useState("");

  const selectedNote = notes.find((note) => note.id === selectedId) ?? null;
  const contentDirty = selectedNote ? selectedNote.title !== title || !documentsEqual(selectedNote.document, editorDocument) : false;
  const dirty = selectedNote ? contentDirty || selectedNote.notebook_id !== editorNotebookId : false;
  const conflict = saveState === "Conflict";

  const visibleNotes = useMemo(() => {
    if (!search.trim()) return notes;
    return searchResults ?? [];
  }, [notes, search, searchResults]);

  const currentNotebook = view === "notebook" ? notebooks.find((item) => item.id === filterId) ?? null : null;
  const currentTag = view === "tag" ? tags.find((item) => item.id === filterId) ?? null : null;
  const noteState: NoteState = view === "archive" ? "archived" : view === "trash" ? "trashed" : "normal";
  const managementView = view === "notebooks" || view === "tags";
  const paneTitle = view === "notebook" ? currentNotebook?.name ?? "Notebook" : view === "tag" ? currentTag?.name ?? "Tag" : view === "archive" ? "Archive" : view === "trash" ? "Trash" : view === "notebooks" ? "Notebooks" : view === "tags" ? "Tags" : "Quick Notes";
  const paneEyebrow = view === "notebook" ? "Notebook" : view === "tag" ? "Tag" : view === "archive" || view === "trash" ? "Library" : managementView ? "Organize" : "Home";

  function applyEditorNote(note: Note | null) {
    if (!note) {
      setSelectedId(null);
      setTitle("");
      setEditorDocument(emptyDocument());
      setEditorNotebookId(null);
      setActiveNoteTags([]);
      setAttachments([]);
      setRevisions([]);
      setSaveState("Saved");
      return;
    }
    setSelectedId(note.id);
    setTitle(note.title);
    setEditorDocument(note.document);
    setEditorNotebookId(note.notebook_id);
    setSaveState("Saved");
  }

  async function loadNoteRelations(noteId: string) {
    const [assignedTags, noteAttachments, noteRevisions] = await Promise.all([
      listNoteTags(noteId),
      listAttachments(noteId),
      listNoteRevisions(noteId),
    ]);
    setActiveNoteTags(assignedTags);
    setAttachments(noteAttachments);
    setRevisions(noteRevisions);
  }

  async function openNote(note: Note | null) {
    applyEditorNote(note);
    setError("");
    if (!note) return;
    try {
      await loadNoteRelations(note.id);
    } catch (caught) {
      setActiveNoteTags([]);
      setAttachments([]);
      setRevisions([]);
      setError(messageFromError(caught));
    }
  }

  async function hydrateWorkspace(authenticatedUser: CurrentUser) {
    const [loadedNotes, loadedNotebooks, loadedTags] = await Promise.all([listNotes(), listNotebooks(), listTags()]);
    setUser(authenticatedUser);
    setNotes(loadedNotes);
    setNotebooks(loadedNotebooks);
    setTags(loadedTags);
    setSearch("");
    setSearchResults(null);
    setSearchError("");
    setAuthState("authenticated");
    await openNote(loadedNotes[0] ?? null);
  }

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      try {
        const currentUser = await getCurrentUser();
        const [loadedNotes, loadedNotebooks, loadedTags] = await Promise.all([listNotes(), listNotebooks(), listTags()]);
        if (cancelled) return;
        setUser(currentUser);
        setNotes(loadedNotes);
        setNotebooks(loadedNotebooks);
        setTags(loadedTags);
        setAuthState("authenticated");
        const first = loadedNotes[0] ?? null;
        applyEditorNote(first);
        if (first) {
          const [assignedTags, noteAttachments, noteRevisions] = await Promise.all([
            listNoteTags(first.id),
            listAttachments(first.id),
            listNoteRevisions(first.id),
          ]);
          if (!cancelled) {
            setActiveNoteTags(assignedTags);
            setAttachments(noteAttachments);
            setRevisions(noteRevisions);
          }
        }
      } catch (caught) {
        if (cancelled) return;
        if (!(caught instanceof ApiError && caught.status === 401)) setError(messageFromError(caught));
        setAuthState("unauthenticated");
      }
    }
    void bootstrap();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const query = search.trim();
    if (authState !== "authenticated" || managementView || !query) {
      setSearchResults(null);
      setSearching(false);
      setSearchError("");
      return;
    }

    let cancelled = false;
    setSearchResults([]);
    setSearching(true);
    setSearchError("");
    const timeout = window.setTimeout(() => {
      void searchNotes({
        query,
        state: noteState,
        notebookId: view === "notebook" ? filterId : null,
        tagId: view === "tag" ? filterId : null,
      })
        .then((results) => {
          if (!cancelled) setSearchResults(results);
        })
        .catch((caught) => {
          if (!cancelled) {
            setSearchResults([]);
            setSearchError(messageFromError(caught));
          }
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [authState, filterId, managementView, noteState, search, view]);

  async function changeView(nextView: WorkspaceView, nextFilterId: string | null = null) {
    setView(nextView);
    setFilterId(nextFilterId);
    setSearch("");
    setSearchResults(null);
    setSearching(false);
    setSearchError("");
    setError("");
    if (nextView === "notebooks" || nextView === "tags") {
      applyEditorNote(null);
      return;
    }
    setBusy(true);
    try {
      const state: NoteState = nextView === "archive" ? "archived" : nextView === "trash" ? "trashed" : "normal";
      const loaded = await listNotes({ state, notebookId: nextView === "notebook" ? nextFilterId : null, tagId: nextView === "tag" ? nextFilterId : null });
      setNotes(loaded);
      await openNote(loaded[0] ?? null);
    } catch (caught) {
      setError(messageFromError(caught));
      setNotes([]);
      applyEditorNote(null);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateNote() {
    setBusy(true);
    setError("");
    setSearch("");
    setSearchResults(null);
    setSearchError("");
    try {
      const note = await createNote(view === "notebook" ? filterId : null);
      if (view === "tag" && filterId) await assignNoteTag(note.id, filterId);
      if (view === "archive" || view === "trash" || managementView) {
        setView("home");
        setFilterId(null);
        const loaded = await listNotes();
        setNotes(loaded);
        await openNote(loaded.find((item) => item.id === note.id) ?? note);
      } else {
        setNotes((current) => [note, ...current]);
        await openNote(note);
      }
    } catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleSave() {
    if (!selectedNote || !dirty || conflict) return;
    setBusy(true);
    setError("");
    setSaveState("Saving…");
    try {
      const updated = await updateNote(selectedNote.id, { title, document: editorDocument, notebook_id: editorNotebookId, expected_content_version: selectedNote.content_version });
      setNotes((current) => current.map((note) => note.id === updated.id ? updated : note));
      setSearchResults((current) => current?.map((note) => note.id === updated.id ? updated : note) ?? null);
      setTitle(updated.title);
      setEditorDocument(updated.document);
      setEditorNotebookId(updated.notebook_id);
      setRevisions(await listNoteRevisions(updated.id));
      setSaveState("Saved");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setSaveState("Conflict");
        setError("This note changed somewhere else. Your local draft has not overwritten the newer server copy. Reload the server version before continuing.");
      } else {
        setSaveState("Not saved");
        setError(messageFromError(caught));
      }
    } finally { setBusy(false); }
  }

  async function handleReloadServerVersion() {
    if (!selectedNote) return;
    setBusy(true);
    setError("");
    try {
      const current = await getNote(selectedNote.id);
      setNotes((items) => items.map((note) => note.id === current.id ? current : note));
      setSearchResults((items) => items?.map((note) => note.id === current.id ? current : note) ?? null);
      applyEditorNote(current);
      await loadNoteRelations(current.id);
    } catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleRevisionRestore(revision: NoteRevision) {
    if (!selectedNote || dirty || conflict) return;
    setBusy(true);
    setError("");
    try {
      const restored = await restoreNoteRevision(selectedNote.id, revision.id, selectedNote.content_version);
      setNotes((items) => items.map((note) => note.id === restored.id ? restored : note));
      setSearchResults((items) => items?.map((note) => note.id === restored.id ? restored : note) ?? null);
      applyEditorNote(restored);
      await loadNoteRelations(restored.id);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setSaveState("Conflict");
        setError("This note changed somewhere else. The historical revision was not restored. Reload the current server version before retrying.");
      } else {
        setError(messageFromError(caught));
      }
    } finally { setBusy(false); }
  }

  async function handleAttachmentUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !selectedNote) return;
    setUploadingAttachment(true);
    setError("");
    try {
      const uploaded = await uploadAttachment(selectedNote.id, file);
      setAttachments((current) => [...current, uploaded]);
    } catch (caught) { setError(messageFromError(caught)); }
    finally { setUploadingAttachment(false); }
  }

  async function handleAttachmentDelete(attachment: Attachment) {
    setUploadingAttachment(true);
    setError("");
    try {
      await deleteAttachment(attachment.id);
      setAttachments((current) => current.filter((item) => item.id !== attachment.id));
    } catch (caught) { setError(messageFromError(caught)); }
    finally { setUploadingAttachment(false); }
  }

  async function handleTrash() {
    if (!selectedNote) return;
    setBusy(true); setError("");
    try { await trashNote(selectedNote.id); const remaining = notes.filter((note) => note.id !== selectedNote.id); setNotes(remaining); setSearchResults((current) => current?.filter((note) => note.id !== selectedNote.id) ?? null); await openNote(remaining[0] ?? null); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleStateChange(state: NoteState) {
    if (!selectedNote) return;
    setBusy(true); setError("");
    try { await updateNote(selectedNote.id, { state }); const remaining = notes.filter((note) => note.id !== selectedNote.id); setNotes(remaining); setSearchResults((current) => current?.filter((note) => note.id !== selectedNote.id) ?? null); await openNote(remaining[0] ?? null); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handlePinToggle() {
    if (!selectedNote) return;
    setBusy(true); setError("");
    try { const updated = await updateNote(selectedNote.id, { is_pinned: !selectedNote.is_pinned }); setNotes((current) => current.map((note) => note.id === updated.id ? updated : note).sort((left, right) => Number(right.is_pinned) - Number(left.is_pinned))); setSearchResults((current) => current?.map((note) => note.id === updated.id ? updated : note).sort((left, right) => Number(right.is_pinned) - Number(left.is_pinned)) ?? null); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleTagToggle(tag: Tag) {
    if (!selectedNote) return;
    setBusy(true); setError("");
    const assigned = activeNoteTags.some((item) => item.id === tag.id);
    try {
      if (assigned) { await removeNoteTag(selectedNote.id, tag.id); setActiveNoteTags((current) => current.filter((item) => item.id !== tag.id)); if (view === "tag" && filterId === tag.id) setSearchResults((current) => current?.filter((note) => note.id !== selectedNote.id) ?? null); }
      else { await assignNoteTag(selectedNote.id, tag.id); setActiveNoteTags((current) => [...current, tag].sort((a, b) => a.name.localeCompare(b.name))); }
    } catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleCreateNotebook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const name = newNotebookName.trim(); if (!name) return;
    setBusy(true); setError("");
    try { const notebook = await createNotebook(name, newNotebookParent || null); setNotebooks((current) => [...current, notebook].sort((a, b) => a.name.localeCompare(b.name))); setNewNotebookName(""); setNewNotebookParent(""); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleDeleteNotebook(notebook: Notebook) {
    setBusy(true); setError("");
    try { await deleteNotebook(notebook.id); setNotebooks((current) => current.filter((item) => item.id !== notebook.id)); if (filterId === notebook.id) await changeView("home"); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleCreateTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const name = newTagName.trim(); if (!name) return;
    setBusy(true); setError("");
    try { const tag = await createTag(name); setTags((current) => [...current, tag].sort((a, b) => a.name.localeCompare(b.name))); setNewTagName(""); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleDeleteTag(tag: Tag) {
    setBusy(true); setError("");
    try { await deleteTag(tag.id); setTags((current) => current.filter((item) => item.id !== tag.id)); setActiveNoteTags((current) => current.filter((item) => item.id !== tag.id)); if (filterId === tag.id) await changeView("home"); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  async function handleLogout() {
    setBusy(true); setError("");
    try { await logoutRequest(); setUser(null); setNotes([]); setNotebooks([]); setTags([]); setSearch(""); setSearchResults(null); setSearchError(""); applyEditorNote(null); setAuthState("unauthenticated"); }
    catch (caught) { setError(messageFromError(caught)); }
    finally { setBusy(false); }
  }

  if (authState === "loading") return <main className="loading-shell" aria-live="polite"><div className="brand-mark" aria-hidden="true">G</div><span>Opening GoreeCloud Notes…</span></main>;
  if (authState === "unauthenticated") return <LoginScreen onAuthenticated={hydrateWorkspace} />;

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="GoreeCloud Notes navigation">
        <div className="brand-row"><div className="brand-mark" aria-hidden="true">G</div><div><strong>GoreeCloud</strong><span>Notes</span></div></div>
        <button className="new-note" type="button" onClick={handleCreateNote} disabled={busy}>+ New note</button>
        <nav>
          <button className={`nav-item${view === "home" ? " active" : ""}`} type="button" onClick={() => void changeView("home")}>Home</button>
          <button className={`nav-item${view === "notebooks" || view === "notebook" ? " active" : ""}`} type="button" onClick={() => void changeView("notebooks")}>Notebooks</button>
          <button className={`nav-item${view === "tags" || view === "tag" ? " active" : ""}`} type="button" onClick={() => void changeView("tags")}>Tags</button>
          <button className={`nav-item${view === "archive" ? " active" : ""}`} type="button" onClick={() => void changeView("archive")}>Archive</button>
          <button className={`nav-item${view === "trash" ? " active" : ""}`} type="button" onClick={() => void changeView("trash")}>Trash</button>
        </nav>
        <div className="sidebar-library">
          {notebooks.slice(0, 5).map((notebook) => <button className={`sidebar-library-item${view === "notebook" && filterId === notebook.id ? " active" : ""}`} type="button" key={notebook.id} onClick={() => void changeView("notebook", notebook.id)}><span aria-hidden="true">▱</span><span>{notebook.name}</span></button>)}
          {tags.slice(0, 5).map((tag) => <button className={`sidebar-library-item${view === "tag" && filterId === tag.id ? " active" : ""}`} type="button" key={tag.id} onClick={() => void changeView("tag", tag.id)}><span aria-hidden="true">#</span><span>{tag.name}</span></button>)}
        </div>
        <div className="sidebar-footer account-footer"><div><span className="status-dot" aria-hidden="true" /><span className="account-name">{user?.display_name}</span></div><button type="button" onClick={handleLogout} disabled={busy}>Sign out</button></div>
      </aside>

      <section className="note-list-pane" aria-label={managementView ? paneTitle : "Notes"}>
        <header className="pane-header"><div><p className="eyebrow">{paneEyebrow}</p><h1>{paneTitle}</h1></div>{!managementView ? <span className="note-count">{search.trim() ? visibleNotes.length : notes.length}</span> : null}</header>
        {error ? <p className="workspace-error" role="alert">{error}</p> : null}
        {searchError ? <p className="workspace-error" role="alert">Search failed: {searchError}</p> : null}
        {view === "notebooks" ? (
          <div className="manager-stack"><form className="manager-create" onSubmit={handleCreateNotebook}><input aria-label="New notebook name" placeholder="New notebook" value={newNotebookName} onChange={(event) => setNewNotebookName(event.target.value)} required /><select aria-label="Parent notebook" value={newNotebookParent} onChange={(event) => setNewNotebookParent(event.target.value)}><option value="">No parent</option>{notebooks.map((notebook) => <option value={notebook.id} key={notebook.id}>{notebook.name}</option>)}</select><button className="primary-button" type="submit" disabled={busy}>Create notebook</button></form><div className="manager-list">{notebooks.map((notebook) => <article className="manager-row" key={notebook.id}><div><strong>{notebook.name}</strong><span>{notebook.parent_id ? "Nested notebook" : "Top-level notebook"}</span></div><div className="manager-actions"><button type="button" onClick={() => void changeView("notebook", notebook.id)}>Open</button><button type="button" onClick={() => void handleDeleteNotebook(notebook)} disabled={busy}>Delete</button></div></article>)}{notebooks.length === 0 ? <div className="empty-list"><strong>No notebooks yet</strong><span>Create a notebook to organize related notes.</span></div> : null}</div></div>
        ) : view === "tags" ? (
          <div className="manager-stack"><form className="manager-create" onSubmit={handleCreateTag}><input aria-label="New tag name" placeholder="New tag" value={newTagName} onChange={(event) => setNewTagName(event.target.value)} required /><button className="primary-button" type="submit" disabled={busy}>Create tag</button></form><div className="manager-list">{tags.map((tag) => <article className="manager-row" key={tag.id}><div><strong>#{tag.name}</strong><span>Private organizational tag</span></div><div className="manager-actions"><button type="button" onClick={() => void changeView("tag", tag.id)}>Open</button><button type="button" onClick={() => void handleDeleteTag(tag)} disabled={busy}>Delete</button></div></article>)}{tags.length === 0 ? <div className="empty-list"><strong>No tags yet</strong><span>Create tags for flexible organization across notebooks.</span></div> : null}</div></div>
        ) : (
          <><label className="search-box"><span aria-hidden="true">⌕</span><input type="search" maxLength={200} placeholder="Search notes" aria-label="Search notes" value={search} onChange={(event) => setSearch(event.target.value)} /></label>{noteState === "normal" ? <button className="quick-capture" type="button" onClick={handleCreateNote} disabled={busy}><span>Take a note…</span><span className="quick-actions" aria-hidden="true">＋</span></button> : null}<div className="notes-stack">{visibleNotes.map((note) => <button className={`note-card${note.id === selectedId ? " selected" : ""}`} type="button" key={note.id} onClick={() => void openNote(note)}><div className="note-card-heading"><h2>{note.title || "Untitled"}</h2>{note.is_pinned ? <span title="Pinned" aria-label="Pinned">●</span> : null}</div><p>{documentToText(note.document) || "Empty note"}</p><small>{new Date(note.updated_at).toLocaleString()}</small></button>)}{visibleNotes.length === 0 ? <div className="empty-list"><strong>{searching ? "Searching…" : search.trim() ? "No matching notes" : `No ${paneTitle.toLocaleLowerCase()} notes`}</strong><span>{searching ? "Searching the private PostgreSQL index." : search.trim() ? "Try another search. Phrase and web-style queries are supported." : "Nothing is stored in this view yet."}</span></div> : null}</div></>
        )}
        <footer className="mobile-source-footer"><span>AGPL-3.0-only</span><span aria-hidden="true"> · </span><SourceLink /></footer>
      </section>

      <section className="editor-pane" aria-label="Note editor">
        {managementView ? (
          <div className="empty-editor organization-editor"><p className="eyebrow">Organization</p><h2>{view === "notebooks" ? "Structure your knowledge." : "Connect ideas across notebooks."}</h2><p>{view === "notebooks" ? "Notebooks provide hierarchy. Deleting a notebook preserves its notes and returns them to the unfiled library." : "Tags provide flexible cross-notebook organization and can be assigned directly from the note editor."}</p></div>
        ) : selectedNote ? (
          <><header className="editor-toolbar"><div className="crumbs">{paneTitle} / {selectedNote.title || "Untitled"}</div><div className="toolbar-actions editor-actions"><span className={`save-state${dirty ? " dirty" : ""}`}>{conflict ? "Conflict" : dirty ? "Unsaved changes" : saveState}</span>{conflict ? <button type="button" onClick={() => void handleReloadServerVersion()} disabled={busy}>Reload server version</button> : null}{noteState === "normal" ? <><button type="button" onClick={() => void handlePinToggle()} disabled={busy || conflict}>{selectedNote.is_pinned ? "Unpin" : "Pin"}</button><button type="button" onClick={() => void handleStateChange("archived")} disabled={busy || conflict}>Archive</button><button type="button" onClick={handleTrash} disabled={busy || conflict}>Trash</button></> : <button type="button" onClick={() => void handleStateChange("normal")} disabled={busy || conflict}>Restore</button>}<button className="save-button" type="button" onClick={handleSave} disabled={busy || !dirty || conflict}>Save</button></div></header>
          <article className="editor-surface live-editor"><p className="eyebrow">Private note</p><input className="title-input" aria-label="Note title" placeholder="Untitled" value={title} onChange={(event) => setTitle(event.target.value)} disabled={conflict} />
            <div className="note-metadata-controls"><label><span>Notebook</span><select value={editorNotebookId ?? ""} onChange={(event) => setEditorNotebookId(event.target.value || null)} disabled={conflict}><option value="">Unfiled</option>{notebooks.map((notebook) => <option value={notebook.id} key={notebook.id}>{notebook.name}</option>)}</select></label><div className="tag-assignment" aria-label="Note tags"><span>Tags</span><div className="tag-chip-list">{tags.map((tag) => { const assigned = activeNoteTags.some((item) => item.id === tag.id); return <button className={`tag-chip${assigned ? " assigned" : ""}`} type="button" aria-pressed={assigned} key={tag.id} onClick={() => void handleTagToggle(tag)} disabled={busy || conflict}>#{tag.name}</button>; })}{tags.length === 0 ? <span className="no-tags">No tags created</span> : null}</div></div></div>
            <section className="attachment-panel" aria-labelledby="attachment-heading"><div className="attachment-heading"><div><span id="attachment-heading">Attachments</span><small>{attachments.length} file{attachments.length === 1 ? "" : "s"}</small></div><label className="attachment-upload"><span>{uploadingAttachment ? "Uploading…" : "Add file"}</span><input type="file" onChange={handleAttachmentUpload} disabled={uploadingAttachment || conflict} /></label></div><div className="attachment-list">{attachments.map((attachment) => <div className="attachment-row" key={attachment.id}><div><a href={attachmentDownloadUrl(attachment.id)}>{attachment.filename}</a><span>{formatBytes(attachment.size_bytes)} · {attachment.media_type}</span></div><button type="button" onClick={() => void handleAttachmentDelete(attachment)} disabled={uploadingAttachment || conflict}>Remove</button></div>)}{attachments.length === 0 ? <span className="attachment-empty">No files attached.</span> : null}</div></section>
            <section className="attachment-panel" aria-labelledby="history-heading"><div className="attachment-heading"><div><span id="history-heading">History</span><small>{revisions.length} recoverable revision{revisions.length === 1 ? "" : "s"}</small></div></div><div className="attachment-list">{revisions.map((revision) => <div className="attachment-row" key={revision.id}><div><strong>Revision {revision.revision_number} · {revision.title || "Untitled"}</strong><span>{new Date(revision.created_at).toLocaleString()} · content version {revision.content_version}</span><span>{documentToText(revision.document).slice(0, 120) || "Empty note"}</span>{revision.change_summary ? <span>{revision.change_summary}</span> : null}</div><button type="button" onClick={() => void handleRevisionRestore(revision)} disabled={busy || dirty || conflict}>Restore</button></div>)}{revisions.length === 0 ? <span className="attachment-empty">No historical revisions yet. A revision is created before eligible content changes.</span> : null}</div><p className="editor-meta">Restoring creates a new content version and preserves the current content as history. Notebook, tags, state, pinning, color, and attachments are not changed.</p></section>
            <p className="editor-meta">Structured GoreeCloud document · content version {selectedNote.content_version}</p><RichNoteEditor noteId={selectedNote.id} value={editorDocument} onChange={setEditorDocument} disabled={busy || conflict} /><div className="callout foundation-callout"><strong>{conflict ? "Conflict protection is active" : "Native rich editing is active"}</strong><span>{conflict ? "The local editor is locked until you reload the current server version, preventing a stale draft from overwriting newer content." : "Rich text is converted through the GoreeCloud-owned document contract and saved with optimistic concurrency protection. Attachments use separate owner-authorized byte storage, and historical content can be restored without rewriting revision history."}</span></div></article></>
        ) : (
          <div className="empty-editor"><p className="eyebrow">GoreeCloud Notes</p><h2>{noteState === "normal" ? "Your private workspace is ready." : `No note selected in ${paneTitle}.`}</h2><p>{noteState === "normal" ? "Create a note to begin building your knowledge library." : "Choose a note from the list or return to Home."}</p>{noteState === "normal" ? <button className="primary-button" type="button" onClick={handleCreateNote} disabled={busy}>Create first note</button> : null}</div>
        )}
        <footer className="source-footer"><span>AGPL-3.0-only</span><span aria-hidden="true"> · </span><SourceLink /></footer>
      </section>
    </main>
  );
}

export default App;
