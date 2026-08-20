import { FormEvent, useEffect, useState } from "react";

import {
  ApiError,
  changePassword,
  getCurrentUser,
  listBrowserSessions,
  revokeOtherBrowserSessions,
  type BrowserSession,
  type CurrentUser,
} from "./api";
import { downloadLibraryExport, saveLibraryExport } from "./libraryExport";

const MIN_PASSWORD_LENGTH = 12;
const MAX_PASSWORD_LENGTH = 1024;

type AccountState = "checking" | "authenticated" | "unauthenticated" | "error";

function accountErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Account security is temporarily unavailable.";
}

function returnToNotes(): void {
  window.location.hash = "";
}

function formatSessionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export default function AccountSecurityPage() {
  const [accountState, setAccountState] = useState<AccountState>("checking");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [sessions, setSessions] = useState<BrowserSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsBusy, setSessionsBusy] = useState(false);
  const [sessionsError, setSessionsError] = useState("");
  const [sessionsSuccess, setSessionsSuccess] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const [exportSuccess, setExportSuccess] = useState("");

  useEffect(() => {
    let active = true;
    void getCurrentUser()
      .then((current) => {
        if (!active) return;
        setUser(current);
        setAccountState("authenticated");
        setSessionsLoading(true);
        void listBrowserSessions()
          .then((activeSessions) => {
            if (!active) return;
            setSessions(activeSessions);
          })
          .catch((loadError: unknown) => {
            if (!active) return;
            if (loadError instanceof ApiError && loadError.status === 401) {
              setUser(null);
              setSessions([]);
              setError("Your session is no longer active. Sign in again to manage account security.");
              setAccountState("unauthenticated");
              return;
            }
            setSessionsError(accountErrorMessage(loadError));
          })
          .finally(() => {
            if (active) setSessionsLoading(false);
          });
      })
      .catch((loadError: unknown) => {
        if (!active) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          setAccountState("unauthenticated");
          return;
        }
        setError(accountErrorMessage(loadError));
        setAccountState("error");
      });
    return () => {
      active = false;
    };
  }, []);

  function expireLocalAccountState(message: string) {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setSessions([]);
    setUser(null);
    setAccountState("unauthenticated");
    setError(message);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    setError("");
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      setError(`New password must contain at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPassword.length > MAX_PASSWORD_LENGTH) {
      setError(`New password must not exceed ${MAX_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("New password must differ from the current password.");
      return;
    }

    setBusy(true);
    try {
      await changePassword(currentPassword, newPassword);
      // The server revokes every session for the account and clears this browser's
      // session/CSRF cookies on success. Do not call logout afterward: there is no
      // valid session left to revoke and doing so would create a misleading error.
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setSessions([]);
      setUser(null);
      setSuccess(true);
      setAccountState("unauthenticated");
    } catch (changeError) {
      if (changeError instanceof ApiError && changeError.status === 401) {
        expireLocalAccountState("Your session is no longer active. Sign in again before changing your password.");
      } else {
        setError(accountErrorMessage(changeError));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeOtherSessions() {
    if (sessionsBusy) return;

    setSessionsError("");
    setSessionsSuccess("");
    setSessionsBusy(true);
    try {
      const result = await revokeOtherBrowserSessions();
      const activeSessions = await listBrowserSessions();
      setSessions(activeSessions);
      setSessionsSuccess(
        result.revoked === 0
          ? "No other active browser sessions needed to be signed out."
          : `Signed out ${result.revoked} other browser session${result.revoked === 1 ? "" : "s"}.`,
      );
    } catch (sessionFailure) {
      if (sessionFailure instanceof ApiError && sessionFailure.status === 401) {
        expireLocalAccountState("Your session is no longer active. Sign in again before managing browser sessions.");
      } else {
        setSessionsError(accountErrorMessage(sessionFailure));
      }
    } finally {
      setSessionsBusy(false);
    }
  }

  async function handleLibraryExport() {
    if (exporting) return;

    setExportError("");
    setExportSuccess("");
    setExporting(true);
    try {
      const download = await downloadLibraryExport();
      saveLibraryExport(download);
      setExportSuccess(
        download.sha256
          ? `Verified ZIP download started. SHA-256: ${download.sha256}`
          : "Verified ZIP download started.",
      );
    } catch (exportFailure) {
      if (exportFailure instanceof ApiError && exportFailure.status === 401) {
        expireLocalAccountState("Your session is no longer active. Sign in again before exporting your library.");
      } else {
        setExportError(accountErrorMessage(exportFailure));
      }
    } finally {
      setExporting(false);
    }
  }

  const otherSessionCount = sessions.filter((session) => !session.current).length;

  return (
    <main className="account-security-page">
      <section className="account-security-card" aria-labelledby="account-security-title">
        <div className="account-security-heading-row">
          <div>
            <p className="eyebrow">GoreeCloud Notes</p>
            <h1 id="account-security-title">Account &amp; Security</h1>
            <p className="account-security-intro">
              Manage private account security and export a portable copy of your Notes library without relying on a hosted identity or storage provider.
            </p>
          </div>
          <button className="secondary-button" type="button" onClick={returnToNotes}>
            Back to Notes
          </button>
        </div>

        {accountState === "checking" ? (
          <div className="account-security-status" role="status">Checking your current session…</div>
        ) : null}

        {accountState === "error" ? (
          <div className="account-security-status account-security-error" role="alert">
            <strong>Account security could not be loaded.</strong>
            <span>{error}</span>
          </div>
        ) : null}

        {accountState === "unauthenticated" ? (
          <div className="account-security-status" role={success ? "status" : undefined}>
            {success ? (
              <>
                <strong>Password changed successfully.</strong>
                <span>Every existing GoreeCloud Notes browser session has been revoked. Sign in again with your new password.</span>
              </>
            ) : (
              <>
                <strong>Sign in required.</strong>
                <span>Open Notes and sign in before changing account security settings or exporting your library.</span>
              </>
            )}
            {error ? <span className="account-security-inline-error">{error}</span> : null}
            <button className="primary-button account-security-signin" type="button" onClick={returnToNotes}>
              Return to sign in
            </button>
          </div>
        ) : null}

        {accountState === "authenticated" && user ? (
          <>
            <div className="account-security-identity" aria-label="Signed-in account">
              <div className="avatar" aria-hidden="true">
                {(user.display_name || user.username).slice(0, 1).toUpperCase()}
              </div>
              <div>
                <strong>{user.display_name}</strong>
                <span>@{user.username}</span>
              </div>
            </div>

            <section className="account-security-portability" aria-labelledby="browser-sessions-heading">
              <div className="account-security-section-heading">
                <h2 id="browser-sessions-heading">Browser sessions</h2>
                <p>
                  Review active server-side Notes sessions and sign out other browsers without ending this session.
                </p>
              </div>
              <p className="field-guidance portability-guidance">
                GoreeCloud Notes shows only session start and expiration times. This view does not require device fingerprinting, IP-history collection, or stored browser secrets.
              </p>
              {sessionsLoading ? <p className="field-guidance" role="status">Loading active sessions…</p> : null}
              {!sessionsLoading && sessions.length === 0 ? (
                <p className="field-guidance">No active session records are currently available.</p>
              ) : null}
              {sessions.map((session) => (
                <div className="account-security-status" key={session.id}>
                  <strong>{session.current ? "Current session" : "Other active session"}</strong>
                  <span>
                    Started {formatSessionTime(session.created_at)} · Expires {formatSessionTime(session.expires_at)}
                  </span>
                </div>
              ))}
              {sessionsError ? <p className="account-security-inline-error" role="alert">{sessionsError}</p> : null}
              {sessionsSuccess ? <p className="account-security-export-success" role="status">{sessionsSuccess}</p> : null}
              <div className="account-security-actions portability-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void handleRevokeOtherSessions()}
                  disabled={busy || exporting || sessionsBusy || sessionsLoading || otherSessionCount === 0}
                >
                  {sessionsBusy ? "Signing out other sessions…" : `Sign out other sessions${otherSessionCount > 0 ? ` (${otherSessionCount})` : ""}`}
                </button>
              </div>
            </section>

            <form className="account-security-form" onSubmit={handleSubmit}>
              <div className="account-security-section-heading">
                <h2>Change password</h2>
                <p>
                  A successful change immediately invalidates every active Notes session, including this one.
                </p>
              </div>

              <label>
                Current password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  minLength={1}
                  maxLength={MAX_PASSWORD_LENGTH}
                  required
                  disabled={busy || exporting || sessionsBusy}
                />
              </label>

              <label>
                New password
                <input
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  minLength={MIN_PASSWORD_LENGTH}
                  maxLength={MAX_PASSWORD_LENGTH}
                  required
                  disabled={busy || exporting || sessionsBusy}
                  aria-describedby="new-password-guidance"
                />
              </label>
              <p id="new-password-guidance" className="field-guidance">
                Use {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters. The server enforces the same boundary and rejects reuse of the current password.
              </p>

              <label>
                Confirm new password
                <input
                  type="password"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  minLength={MIN_PASSWORD_LENGTH}
                  maxLength={MAX_PASSWORD_LENGTH}
                  required
                  disabled={busy || exporting || sessionsBusy}
                />
              </label>

              {error ? <p className="account-security-inline-error" role="alert">{error}</p> : null}

              <div className="account-security-actions">
                <button
                  className="primary-button"
                  type="submit"
                  disabled={busy || exporting || sessionsBusy || !currentPassword || !newPassword || !confirmPassword}
                >
                  {busy ? "Changing password…" : "Change password"}
                </button>
              </div>
            </form>

            <section className="account-security-portability" aria-labelledby="portable-export-heading">
              <div className="account-security-section-heading">
                <h2 id="portable-export-heading">Data portability</h2>
                <p>
                  Download a verified, provider-neutral ZIP containing your native Notes library, organization, revision history, attachment metadata, actual attachment bytes, and preserved migration provenance when present.
                </p>
              </div>
              <p className="field-guidance portability-guidance">
                Password hashes, browser sessions, CSRF material, login-rate state, deployment secrets, derived search indexes, and internal attachment storage paths are excluded from the portable bundle.
              </p>
              {exportError ? <p className="account-security-inline-error" role="alert">{exportError}</p> : null}
              {exportSuccess ? <p className="account-security-export-success" role="status">{exportSuccess}</p> : null}
              <div className="account-security-actions portability-actions">
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void handleLibraryExport()}
                  disabled={busy || exporting || sessionsBusy}
                >
                  {exporting ? "Building verified export…" : "Download full library"}
                </button>
              </div>
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}