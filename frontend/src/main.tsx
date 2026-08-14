import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import AccountSecurityPage from "./AccountSecurityPage";
import App from "./App";
import "./styles.css";
import "./organization.css";
import "./rich-editor.css";
import "./attachments.css";
import "./account-security.css";

function Root() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    function handleHashChange() {
      setHash(window.location.hash);
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  if (hash === "#account-security") {
    return <AccountSecurityPage />;
  }

  return (
    <>
      <App />
      <a className="account-security-launcher" href="#account-security">
        Account &amp; Security
      </a>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
