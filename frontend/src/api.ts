export type CurrentUser = {
  id: string;
  username: string;
  display_name: string;
};

export type DocumentBlock = {
  type: string;
  text?: string;
};

export type NoteDocument = {
  format: "goreecloud.blocks";
  version: 1;
  blocks: DocumentBlock[];
};

export type NoteState = "normal" | "archived" | "trashed";

export type Notebook = {
  id: string;
  parent_id: string | null;
  name: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type Tag = {
  id: string;
  name: string;
  normalized_name: string;
  color: string | null;
  created_at: string;
  updated_at: string;
};

export type Note = {
  id: string;
  notebook_id: string | null;
  title: string;
  document: NoteDocument;
  document_schema: number;
  content_version: number;
  state: NoteState;
  is_pinned: boolean;
  color: string | null;
  created_at: string;
  updated_at: string;
};

export type NoteListOptions = {
  state?: NoteState;
  notebookId?: string | null;
  tagId?: string | null;
  query?: string;
};

export type NotePatch = Partial<
  Pick<Note, "title" | "document" | "notebook_id" | "state" | "is_pinned" | "color">
> & {
  expected_content_version?: number;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const item of document.cookie.split(";")) {
    const clean = item.trim();
    if (clean.startsWith(prefix)) {
      return decodeURIComponent(clean.slice(prefix.length));
    }
  }
  return null;
}

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  options: { csrf?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (options.csrf) {
    const csrfToken = readCookie("goreecloud_notes_csrf");
    if (!csrfToken) {
      throw new ApiError(403, "The security token for this session is unavailable. Please sign in again.");
    }
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the status-derived message when the response is intentionally empty
      // or does not contain JSON.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function emptyDocument(): NoteDocument {
  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks: [],
  };
}

export function documentToText(document: NoteDocument | Record<string, unknown>): string {
  if (
    document.format !== "goreecloud.blocks" ||
    document.version !== 1 ||
    !Array.isArray(document.blocks)
  ) {
    return "";
  }

  return document.blocks
    .filter((block): block is DocumentBlock => typeof block === "object" && block !== null)
    .map((block) => (typeof block.text === "string" ? block.text : ""))
    .join("\n\n");
}

export function textToDocument(value: string): NoteDocument {
  const blocks = value
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trimEnd())
    .filter((paragraph) => paragraph.length > 0)
    .map((text) => ({ type: "paragraph", text }));

  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks,
  };
}

export function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/me");
}

export function login(username: string, password: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" }, { csrf: true });
}

export function listNotebooks(): Promise<Notebook[]> {
  return apiFetch<Notebook[]>("/notebooks");
}

export function createNotebook(name: string, parentId: string | null = null): Promise<Notebook> {
  return apiFetch<Notebook>(
    "/notebooks",
    {
      method: "POST",
      body: JSON.stringify({ name, parent_id: parentId }),
    },
    { csrf: true },
  );
}

export function updateNotebook(
  notebookId: string,
  payload: { name?: string; parent_id?: string | null; sort_order?: number },
): Promise<Notebook> {
  return apiFetch<Notebook>(
    `/notebooks/${encodeURIComponent(notebookId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    { csrf: true },
  );
}

export function deleteNotebook(notebookId: string): Promise<void> {
  return apiFetch<void>(
    `/notebooks/${encodeURIComponent(notebookId)}`,
    { method: "DELETE" },
    { csrf: true },
  );
}

export function listTags(): Promise<Tag[]> {
  return apiFetch<Tag[]>("/tags");
}

export function createTag(name: string, color: string | null = null): Promise<Tag> {
  return apiFetch<Tag>(
    "/tags",
    { method: "POST", body: JSON.stringify({ name, color }) },
    { csrf: true },
  );
}

export function updateTag(
  tagId: string,
  payload: { name?: string; color?: string | null },
): Promise<Tag> {
  return apiFetch<Tag>(
    `/tags/${encodeURIComponent(tagId)}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    { csrf: true },
  );
}

export function deleteTag(tagId: string): Promise<void> {
  return apiFetch<void>(
    `/tags/${encodeURIComponent(tagId)}`,
    { method: "DELETE" },
    { csrf: true },
  );
}

export function listNotes(options: NoteListOptions = {}): Promise<Note[]> {
  const params = new URLSearchParams();
  params.set("state", options.state ?? "normal");
  if (options.notebookId) {
    params.set("notebook_id", options.notebookId);
  }
  if (options.tagId) {
    params.set("tag_id", options.tagId);
  }
  if (options.query?.trim()) {
    params.set("q", options.query.trim());
  }
  return apiFetch<Note[]>(`/notes?${params.toString()}`);
}

export function createNote(notebookId: string | null = null): Promise<Note> {
  return apiFetch<Note>(
    "/notes",
    {
      method: "POST",
      body: JSON.stringify({
        title: "",
        document: emptyDocument(),
        notebook_id: notebookId,
      }),
    },
    { csrf: true },
  );
}

export function updateNote(noteId: string, payload: NotePatch): Promise<Note> {
  return apiFetch<Note>(
    `/notes/${encodeURIComponent(noteId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    { csrf: true },
  );
}

export function trashNote(noteId: string): Promise<void> {
  return apiFetch<void>(
    `/notes/${encodeURIComponent(noteId)}`,
    { method: "DELETE" },
    { csrf: true },
  );
}

export function listNoteTags(noteId: string): Promise<Tag[]> {
  return apiFetch<Tag[]>(`/notes/${encodeURIComponent(noteId)}/tags`);
}

export function assignNoteTag(noteId: string, tagId: string): Promise<void> {
  return apiFetch<void>(
    `/notes/${encodeURIComponent(noteId)}/tags/${encodeURIComponent(tagId)}`,
    { method: "PUT" },
    { csrf: true },
  );
}

export function removeNoteTag(noteId: string, tagId: string): Promise<void> {
  return apiFetch<void>(
    `/notes/${encodeURIComponent(noteId)}/tags/${encodeURIComponent(tagId)}`,
    { method: "DELETE" },
    { csrf: true },
  );
}
