const navigation = [
  "Home",
  "All Notes",
  "Notebooks",
  "Tags",
  "Shortcuts",
  "Archive",
  "Trash",
];

const sampleNotes = [
  {
    title: "Welcome to GoreeCloud Notes",
    preview: "The native knowledge workspace foundation is ready for development.",
    meta: "Foundation · just now",
  },
  {
    title: "Quick Notes",
    preview: "Fast capture will remain a first-class workflow alongside notebooks and knowledge tools.",
    meta: "Product direction",
  },
  {
    title: "Portable by design",
    preview: "Markdown interoperability, exports, migration, and recovery stay part of the architecture.",
    meta: "Data ownership",
  },
];

function SourceLink() {
  return (
    <a className="source-link" href="https://github.com/GoreeCloud/goreecloud-notes">
      Source code
    </a>
  );
}

function App() {
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

        <button className="new-note" type="button">+ New note</button>

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

        <div className="sidebar-footer">
          <span className="status-dot" aria-hidden="true" />
          Native foundation
        </div>
      </aside>

      <section className="note-list-pane" aria-label="Notes">
        <header className="pane-header">
          <div>
            <p className="eyebrow">Home</p>
            <h1>Quick Notes</h1>
          </div>
          <button className="icon-button" type="button" aria-label="More options">•••</button>
        </header>

        <label className="search-box">
          <span aria-hidden="true">⌕</span>
          <input type="search" placeholder="Search notes" aria-label="Search notes" />
        </label>

        <button className="quick-capture" type="button">
          <span>Take a note…</span>
          <span className="quick-actions" aria-hidden="true">☑  ＋</span>
        </button>

        <div className="notes-stack">
          {sampleNotes.map((note, index) => (
            <article className={`note-card${index === 0 ? " selected" : ""}`} key={note.title}>
              <h2>{note.title}</h2>
              <p>{note.preview}</p>
              <small>{note.meta}</small>
            </article>
          ))}
        </div>

        <footer className="mobile-source-footer">
          <span>AGPL-3.0-only</span>
          <span aria-hidden="true"> · </span>
          <SourceLink />
        </footer>
      </section>

      <section className="editor-pane" aria-label="Note editor">
        <header className="editor-toolbar">
          <div className="crumbs">Home / Quick Notes</div>
          <div className="toolbar-actions">
            <button type="button">☆</button>
            <button type="button">•••</button>
          </div>
        </header>

        <article className="editor-surface">
          <p className="eyebrow">Native GoreeCloud Notes</p>
          <h2>Welcome to GoreeCloud Notes</h2>
          <p className="editor-meta">Foundation workspace · autosave and rich editing are not wired yet</p>
          <p>
            This is the first native Glaze UI shell for the GoreeCloud Notes knowledge workspace.
            It establishes the three-pane desktop direction while keeping Quick Notes visible as a
            low-friction capture experience.
          </p>
          <div className="callout">
            <strong>Milestone 0</strong>
            <span>Repository, API, database, security, CI, and migration foundations come first.</span>
          </div>
          <h3>What comes next</h3>
          <ul>
            <li>Native users and authorization boundaries</li>
            <li>Notes, notebooks, nested notebooks, and tags</li>
            <li>Structured rich-text editing with Markdown interoperability</li>
            <li>Search, attachments, revision history, and portable exports</li>
          </ul>
        </article>

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
