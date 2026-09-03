import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import AccountSecurityPage from "./AccountSecurityPage";
import App from "./App";
import { AppearanceControl } from "./AppearanceControl";
import { initializeAppearancePreference } from "./appearance";
import { KnowledgeHome } from "./KnowledgeHome";
import { WorkspaceNavigationGuard } from "./WorkspaceNavigationGuard";
import "./glaze/glaze.css";
import "./glaze/glaze.accessibility.css";
import "./styles.css";
import "./organization.css";
import "./rich-editor.css";
import "./attachments.css";
import "./account-security.css";
import "./knowledge-home.css";
import "./glaze-theme-bridge.css";
import "./glaze-foundation.css";

initializeAppearancePreference();

function Root() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    function handleHashChange() {
      setHash(window.location.hash);
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const accountSecurityOpen = hash === "#account-security";
  const knowledgeHomeOpen = hash === "#knowledge-home";

  function openWorkspace() {
    window.location.hash = "";
  }

  return (
    <div className="notes-root glaze-canvas">
      {accountSecurityOpen ? <AccountSecurityPage /> : knowledgeHomeOpen ? <KnowledgeHome onOpenWorkspace={openWorkspace} /> : <App />}
      <aside className="glaze-utility-dock glaze-overlay" aria-label="Application controls">
        <AppearanceControl />
        {!accountSecurityOpen ? (
          <a className="account-security-launcher glaze-button" href={knowledgeHomeOpen ? "#" : "#knowledge-home"}>
            {knowledgeHomeOpen ? "Notes workspace" : "Knowledge Home"}
          </a>
        ) : null}
        {!accountSecurityOpen ? (
          <a
            className="account-security-launcher glaze-button"
            href="#account-security"
            target="_blank"
            rel="noopener"
            title="Open Account & Security in a new tab so the current Notes draft remains open"
          >
            Account &amp; Security
          </a>
        ) : null}
      </aside>
      <WorkspaceNavigationGuard />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
