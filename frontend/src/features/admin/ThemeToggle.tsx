/**
 * Theme switch for the admin top bar: daylight, night, or follow the OS.
 *
 * Three native radios inside a fieldset rather than three buttons, because that
 * is what the control actually is — one choice out of three — and it buys the
 * roving-focus keyboard behavior (arrow keys move the selection, Tab enters and
 * leaves the group once) without a line of ARIA or a keydown handler.
 *
 * Each option keeps a real text label in the accessibility tree at every width;
 * below the top bar's breakpoint the label is clipped visually rather than
 * removed, so the control shrinks to its icons without going mute to a screen
 * reader.
 */

import type { ThemePreference } from "./theme";
import "./ThemeToggle.css";

/**
 * Icon geometry from Heroicons (MIT), solid 24px set — one library, one weight,
 * so the three marks sit together instead of looking sourced from three places.
 */
function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M12 2.25a.75.75 0 0 1 .75.75v2.25a.75.75 0 0 1-1.5 0V3a.75.75 0 0 1 .75-.75Zm0 5.25a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9Zm6.894-1.334a.75.75 0 0 0-1.06-1.06l-1.591 1.59a.75.75 0 1 0 1.06 1.061l1.591-1.591ZM21.75 12a.75.75 0 0 1-.75.75h-2.25a.75.75 0 0 1 0-1.5H21a.75.75 0 0 1 .75.75Zm-3.916 6.894a.75.75 0 0 0 1.06-1.06l-1.59-1.591a.75.75 0 1 0-1.061 1.06l1.591 1.591ZM12 18a.75.75 0 0 1 .75.75V21a.75.75 0 0 1-1.5 0v-2.25A.75.75 0 0 1 12 18Zm-4.242-.697a.75.75 0 0 0-1.061-1.06l-1.591 1.59a.75.75 0 0 0 1.06 1.061l1.592-1.591ZM6 12a.75.75 0 0 1-.75.75H3a.75.75 0 0 1 0-1.5h2.25A.75.75 0 0 1 6 12Zm.697-5.303a.75.75 0 0 0 1.06-1.06l-1.59-1.591a.75.75 0 0 0-1.061 1.06l1.591 1.591Z"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M21.752 15.002A9.718 9.718 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 9.002-5.998Z"
      />
    </svg>
  );
}

function SystemIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        fillRule="evenodd"
        clipRule="evenodd"
        d="M2.25 5.25a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3V15a3 3 0 0 1-3 3h-3v.257c0 .597.237 1.17.659 1.591l.621.622a.75.75 0 0 1-.53 1.28h-9a.75.75 0 0 1-.53-1.28l.621-.622a2.25 2.25 0 0 0 .659-1.59V18h-3a3 3 0 0 1-3-3V5.25Zm1.5 0v7.5a1.5 1.5 0 0 0 1.5 1.5h13.5a1.5 1.5 0 0 0 1.5-1.5v-7.5a1.5 1.5 0 0 0-1.5-1.5H5.25a1.5 1.5 0 0 0-1.5 1.5Z"
      />
    </svg>
  );
}

const OPTIONS: ReadonlyArray<{
  value: ThemePreference;
  label: string;
  icon: React.ReactNode;
}> = [
  { value: "light", label: "Claro", icon: <SunIcon /> },
  { value: "dark", label: "Oscuro", icon: <MoonIcon /> },
  { value: "system", label: "Sistema", icon: <SystemIcon /> },
];

interface ThemeToggleProps {
  preference: ThemePreference;
  onChange: (preference: ThemePreference) => void;
}

export function ThemeToggle({ preference, onChange }: ThemeToggleProps) {
  return (
    <fieldset className="theme-toggle">
      <legend className="sr-only">Tema del panel</legend>
      {OPTIONS.map((option) => (
        <label key={option.value} className="theme-toggle__option">
          <input
            type="radio"
            className="theme-toggle__input"
            name="admin-theme"
            value={option.value}
            checked={preference === option.value}
            onChange={() => onChange(option.value)}
          />
          <span className="theme-toggle__icon">{option.icon}</span>
          <span className="theme-toggle__label">{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
