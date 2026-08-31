import { useEffect, useState, type ChangeEvent } from "react";

import {
  APPEARANCE_STORAGE_KEY,
  applyAppearancePreference,
  readAppearancePreference,
  saveAppearancePreference,
  type AppearancePreference,
} from "./appearance";

const APPEARANCE_OPTIONS: Array<{ value: AppearancePreference; label: string }> = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function AppearanceControl() {
  const [preference, setPreference] = useState<AppearancePreference>(() => readAppearancePreference());

  useEffect(() => {
    function handleStorage(event: StorageEvent) {
      if (event.key !== APPEARANCE_STORAGE_KEY && event.key !== null) return;
      const nextPreference = readAppearancePreference();
      setPreference(nextPreference);
      applyAppearancePreference(nextPreference);
    }

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextPreference = event.target.value as AppearancePreference;
    setPreference(nextPreference);
    saveAppearancePreference(nextPreference);
  }

  return (
    <label className="appearance-control">
      <span>Appearance</span>
      <select
        className="glaze-select appearance-select"
        aria-label="Appearance"
        value={preference}
        onChange={handleChange}
      >
        {APPEARANCE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
