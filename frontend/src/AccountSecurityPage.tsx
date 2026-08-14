import { FormEvent, useEffect, useState } from "react";

import { ApiError, changePassword, getCurrentUser, type CurrentUser } from "./api";

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

export default function AccountSecurityPage() {
  const [accountState, setAccountState] = useState<AccountState>("checking");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    let active = true;
    void getCurrentUser()
      .then((current) => {
        if (!active) return;
        setUser(current);
        setAccountState("authenticated");
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
      setUser(null);
      setSuccess(true);
      setAccountState("unauthenticated");
    } catch (changeError) {
      if (changeError instanceof ApiError && changeError.status === 401) {
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
        setUser(null);
        setAccountState("unauthenticated");
        setError("Your session is no longer active. Sign in again before changing your password.");
      } else {
        setError(accountErrorMessage(changeError));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="account-security-page">
      <section className="account-security-card" aria-labelledby="account-security-title">
        <div className="account-security-heading-row">
          <div>
            <p className="eyebrow">GoreeCloud Notes</p>
            <h1 id="account-security-title">Account &amp; Security</h1>
            <p className="account-security-intro">
              Change your private Notes password without sending credentials to an email, SMS, or hosted identity provider.
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
                <span>Open Notes and sign in before changing account security settings.</span>
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
                  disabled={busy}
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
                  disabled={busy}
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
                  disabled={busy}
                />
              </label>

              {error ? <p className="account-security-inline-error" role="alert">{error}</p> : null}

              <div className="account-security-actions">
                <button
                  className="primary-button"
                  type="submit"
                  disabled={busy || !currentPassword || !newPassword || !confirmPassword}
                >
                  {busy ? "Changing password…" : "Change password"}
                </button>
              </div>
            </form>
          </>
        ) : null}
      </section>
    </main>
  );
}
