import {
  documentToPlainText,
  emptyDocument,
  sanitizeDocument,
  type NoteDocument,
} from "./document";

export type { NoteDocument } from "./document";

export type CurrentUser = {
  id: string;
  username: string;
  display_name: string;
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

export type Attachment = {
  id: string;
  note_id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
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

export type NoteRevision = {
  id: string;
  revision_number: number;
  content_version: number;
  title: string;
  document: NoteDocument;
  document_schema: number;
  created_at: string;
  change_summary: string | null;
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

const SAFE_IMAGE_PREVIEW_MEDIA_TYPES = new Set([
  "image/avif",
  "image/gif",
  "image/jpeg",
  "image/png",
  "image/webp",
]);

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
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
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
      // Keep the status-derived message for intentionally empty/non-JSON errors.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

function normalizeNote(note: Note): Note {
  return { ...note, document: sanitizeDocument(note.document) };
}

function normalizeRevision(revision: NoteRevision): NoteRevision {
  return { ...revision, document: sanitizeDocument(revision.document) };
}

export function documentToText(document: NoteDocument): string {
  return documentToPlainText(document);
}

export function textToDocument(text: string): NoteDocument {
  const normalized = text.replace(/\r\n?/g, "\n");
  const paragraphs = normalized.split(/\n{2,}/).map((value) => value.trimEnd());
  const blocks = paragraphs
    .filter((value, index) => value.length > 0 || index === 0)
    .map((value) => ({
      type: "paragraph" as const,
      content: value.length > 0
        ? [{ type: "text" as const, text: value.replace(/\n/g, " ") }]
        : [],
    }));

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

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return apiFetch<void>(
    "/auth/password",
    {
      method: "POST",
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
    { csrf: true },
  );
}

export function listNotebooks(): Promise<Notebook[]> {
  return apiFetch<Notebook[]>("/notebooks");
}

export function createNotebook(name: string, parentId: string | null = null): Promise<Notebook> {
  return apiFetch<Notebook>(
    "/notebooks",
    { method: "POST", body: JSON.stringify({ name, parent_id: parentId }) },
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

export async function listNotes(options: NoteListOptions = {}): Promise<Note[]> {
  const params = new URLSearchParams();
  params.set("state", options.state ?? "normal");
  if (options.notebookId) params.set("notebook_id", options.notebookId);
  if (options.tagId) params.set("tag_id", options.tagId);
  if (options.query?.trim()) params.set("q", options.query.trim());
  return (await apiFetch<Note[]>(`/notes?${params.toString()}`)).map(normalizeNote);
}

export async function searchNotes(options: NoteListOptions & { query: string }): Promise<Note[]> {
  const query = options.query.trim();
  if (!query) return [];

  const params = new URLSearchParams({ q: query, state: options.state ?? "normal" });
  if (options.notebookId) params.set("notebook_id", options.notebookId);
  if (options.tagId) params.set("tag_id", options.tagId);
  return (await apiFetch<Note[]>(`/search/notes?${params.toString()}`)).map(normalizeNote);
}

export async function createNote(notebookId: string | null = null): Promise<Note> {
  return normalizeNote(
    await apiFetch<Note>(
      "/notes",
      {
        method: "POST",
        body: JSON.stringify({ title: "", document: emptyDocument(), notebook_id: notebookId }),
      },
      { csrf: true },
    ),
  );
}

export async function getNote(noteId: string): Promise<Note> {
  return normalizeNote(await apiFetch<Note>(`/notes/${encodeURIComponent(noteId)}`));
}

export async function updateNote(noteId: string, payload: NotePatch): Promise<Note> {
  return normalizeNote(
    await apiFetch<Note>(
      `/notes/${encodeURIComponent(noteId)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      { csrf: true },
    ),
  );
}

export async function listNoteRevisions(noteId: string): Promise<NoteRevision[]> {
  return (await apiFetch<NoteRevision[]>(`/notes/${encodeURIComponent(noteId)}/revisions`)).map(
    normalizeRevision,
  );
}

export async function restoreNoteRevision(
  noteId: string,
  revisionId: string,
  expectedContentVersion: number,
): Promise<Note> {
  return normalizeNote(
    await apiFetch<Note>(
      `/notes/${encodeURIComponent(noteId)}/revisions/${encodeURIComponent(revisionId)}/restore`,
      {
        method: "POST",
        body: JSON.stringify({ expected_content_version: expectedContentVersion }),
      },
      { csrf: true },
    ),
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

export function listAttachments(noteId: string): Promise<Attachment[]> {
  return apiFetch<Attachment[]>(`/notes/${encodeURIComponent(noteId)}/attachments`);
}

export function uploadAttachment(noteId: string, file: File): Promise<Attachment> {
  const params = new URLSearchParams({ filename: file.name });
  return apiFetch<Attachment>(
    `/notes/${encodeURIComponent(noteId)}/attachments?${params.toString()}`,
    {
      method: "POST",
      headers: { "Content-Type": file.type || "application/octet-stream" },
      body: file,
    },
    { csrf: true },
  );
}

export function deleteAttachment(attachmentId: string): Promise<void> {
  return apiFetch<void>(
    `/attachments/${encodeURIComponent(attachmentId)}`,
    { method: "DELETE" },
    { csrf: true },
  );
}

export function attachmentDownloadUrl(attachmentId: string): string {
  return `/api/v1/attachments/${encodeURIComponent(attachmentId)}`;
}

export function isAttachmentPreviewable(attachment: Attachment): boolean {
  return SAFE_IMAGE_PREVIEW_MEDIA_TYPES.has(attachment.media_type.toLocaleLowerCase());
}

export function attachmentPreviewUrl(attachmentId: string): string {
  return `/api/v1/attachments/${encodeURIComponent(attachmentId)}/preview`;
}