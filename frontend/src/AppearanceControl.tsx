import { useState, type ChangeEvent } from "react";

import {
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
