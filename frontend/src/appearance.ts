export type AppearancePreference = "system" | "light" | "dark";

export const APPEARANCE_STORAGE_KEY = "goreecloud.notes.appearance";
const APPEARANCE_VALUES = new Set<AppearancePreference>(["system", "light", "dark"]);

function isAppearancePreference(value: string | null): value is AppearancePreference {
  return value !== null && APPEARANCE_VALUES.has(value as AppearancePreference);
}

export function readAppearancePreference(): AppearancePreference {
  try {
    const stored = window.localStorage.getItem(APPEARANCE_STORAGE_KEY);
    return isAppearancePreference(stored) ? stored : "system";
  } catch {
    // Private browsing and hardened browser profiles may deny local storage.
    // System appearance remains a complete, privacy-preserving fallback.
    return "system";
  }
}

export function applyAppearancePreference(preference: AppearancePreference): void {
  const root = document.documentElement;
  root.dataset.appearancePreference = preference;

  if (preference === "system") {
    root.removeAttribute("data-theme");
    return;
  }

  root.dataset.theme = preference;
}

export function saveAppearancePreference(preference: AppearancePreference): void {
  applyAppearancePreference(preference);
  try {
    if (preference === "system") {
      window.localStorage.removeItem(APPEARANCE_STORAGE_KEY);
    } else {
      window.localStorage.setItem(APPEARANCE_STORAGE_KEY, preference);
    }
  } catch {
    // Appearance is intentionally client-local and noncritical. If persistence is
    // unavailable, the active document still receives the selected appearance.
  }
}

export function initializeAppearancePreference(): AppearancePreference {
  const preference = readAppearancePreference();
  applyAppearancePreference(preference);
  return preference;
}
