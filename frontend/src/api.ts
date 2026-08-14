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

export type Note = {
  id: string;
  notebook_id: string | null;
  title: string;
  document: NoteDocument;
  document_schema: number;
  state: "normal" | "archived" | "trashed";
  is_pinned: boolean;
  color: string | null;
  created_at: string;
  updated_at: string;
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

export function listNotes(): Promise<Note[]> {
  return apiFetch<Note[]>("/notes?state=normal");
}

export function createNote(): Promise<Note> {
  return apiFetch<Note>(
    "/notes",
    {
      method: "POST",
      body: JSON.stringify({ title: "", document: emptyDocument() }),
    },
    { csrf: true },
  );
}

export function updateNote(
  noteId: string,
  payload: Pick<Note, "title" | "document">,
): Promise<Note> {
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
