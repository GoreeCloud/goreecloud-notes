import { ApiError } from "./api";

export type LibraryExportDownload = {
  blob: Blob;
  filename: string;
  sha256: string | null;
};

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

function filenameFromDisposition(value: string | null): string {
  if (!value) return "goreecloud-notes-library.zip";
  const match = /filename="?([^";]+)"?/i.exec(value);
  if (!match?.[1]) return "goreecloud-notes-library.zip";

  const filename = match[1].trim();
  if (!filename || filename.includes("/") || filename.includes("\\")) {
    return "goreecloud-notes-library.zip";
  }
  return filename;
}

export async function downloadLibraryExport(): Promise<LibraryExportDownload> {
  const csrfToken = readCookie("goreecloud_notes_csrf");
  if (!csrfToken) {
    throw new ApiError(403, "The security token for this session is unavailable. Please sign in again.");
  }

  const response = await fetch("/api/v1/exports/library", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrfToken },
  });

  if (!response.ok) {
    let message = `Export failed with status ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-derived message when an intermediary returns non-JSON content.
    }
    throw new ApiError(response.status, message);
  }

  const contentType = response.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "application/zip") {
    throw new ApiError(502, "The server returned an unexpected export format.");
  }

  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
    sha256: response.headers.get("X-GoreeCloud-Export-SHA256"),
  };
}

export function saveLibraryExport(download: LibraryExportDownload): void {
  const url = URL.createObjectURL(download.blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = download.filename;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
