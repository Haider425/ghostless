/*
  Display and search preferences. Kept in a cookie so the server can render
  pages in the right theme and text size on the first load, and saved to the
  account for signed-in users so they follow them to other devices.
  Shared by server and client code.
*/

export type Theme = "system" | "light" | "dark";
export type TextSize = "sm" | "md" | "lg" | "xl";
export type Density = "comfortable" | "compact";
export type LocationPref = "any" | "canada" | "remote" | "canada_or_remote";

export interface Prefs {
  theme: Theme;
  text_size: TextSize;
  density: Density;
  reduce_motion: boolean;
  underline_links: boolean;
  default_location: LocationPref;
  hide_high_risk: boolean;
  analytics: boolean;
}

export const DEFAULT_PREFS: Prefs = {
  theme: "system",
  text_size: "md",
  density: "comfortable",
  reduce_motion: false,
  underline_links: false,
  default_location: "any",
  hide_high_risk: false,
  analytics: true,
};

export const PREFS_COOKIE = "gl_prefs";
export const PREFS_MAX_AGE = 60 * 60 * 24 * 365;

const ALLOWED: { [K in keyof Prefs]: readonly Prefs[K][] } = {
  theme: ["system", "light", "dark"],
  text_size: ["sm", "md", "lg", "xl"],
  density: ["comfortable", "compact"],
  reduce_motion: [true, false],
  underline_links: [true, false],
  default_location: ["any", "canada", "remote", "canada_or_remote"],
  hide_high_risk: [true, false],
  analytics: [true, false],
};

/** Keep only known keys with allowed values; anything else falls back to the default. */
export function cleanPrefs(value: unknown): Prefs {
  const input = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  const out = { ...DEFAULT_PREFS };
  for (const key of Object.keys(ALLOWED) as (keyof Prefs)[]) {
    if ((ALLOWED[key] as readonly unknown[]).includes(input[key])) {
      (out as Record<string, unknown>)[key] = input[key];
    }
  }
  return out;
}

export function parsePrefsCookie(raw: string | undefined): Prefs {
  if (!raw) return DEFAULT_PREFS;
  try {
    return cleanPrefs(JSON.parse(decodeURIComponent(raw)));
  } catch {
    return DEFAULT_PREFS;
  }
}

export function serializePrefs(prefs: Prefs): string {
  return encodeURIComponent(JSON.stringify(prefs));
}

/** Attributes for <html>, so CSS applies the settings before anything paints. */
export function htmlAttributes(prefs: Prefs): Record<string, string | undefined> {
  return {
    "data-theme": prefs.theme === "system" ? undefined : prefs.theme,
    "data-text": prefs.text_size === "md" ? undefined : prefs.text_size,
    "data-density": prefs.density === "compact" ? "compact" : undefined,
    "data-motion": prefs.reduce_motion ? "reduce" : undefined,
    "data-underline": prefs.underline_links ? "" : undefined,
  };
}
