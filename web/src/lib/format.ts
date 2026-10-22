import type { GhostRisk, Job, Level, RoleType } from "./api-types";

export const LEVEL_LABELS: Record<Level, string> = {
  intern: "Intern / co-op",
  new_grad: "New grad",
  mid: "Mid level",
  senior: "Senior",
};

export const ROLE_LABELS: Record<RoleType, string> = {
  sde: "Software",
  data_eng: "Data engineering",
  data: "Data and analytics",
  ml: "AI and ML",
  hardware: "Hardware and embedded",
  security: "Security",
  other: "Non-tech",
};

/** Short names for the role tabs. */
export const ROLE_TABS: Record<RoleType, string> = {
  sde: "Software",
  data_eng: "Data engineering",
  data: "Data and analytics",
  ml: "AI and ML",
  hardware: "Hardware",
  security: "Security",
  other: "Non-tech",
};

/** Role names for use mid-sentence, where acronyms must stay capitalized. */
export const ROLE_LABELS_INLINE: Record<RoleType, string> = {
  sde: "software",
  data_eng: "data engineering",
  data: "data and analytics",
  ml: "AI and ML",
  hardware: "hardware",
  security: "security",
  other: "non-tech",
};

export const RISK_LABELS: Record<GhostRisk, string> = {
  low: "No flags",
  medium: "Some flags",
  high: "High ghost risk",
};

export const FLAG_TEXT: Record<string, { short: string; long: string }> = {
  not_existing_vacancy: {
    short: "Not a real opening",
    long: "The employer's own posting says it is not for an existing vacancy, usually a talent pool.",
  },
  reposted: {
    short: "Reposted",
    long: "This role was posted before, taken down, and put back up under a new listing.",
  },
  duplicate_posting: {
    short: "Duplicate listing",
    long: "Identical copies of this role are live at the same time.",
  },
  open_unusually_long: {
    short: "Open unusually long",
    long: "It has been open far longer than this employer usually takes to fill the role.",
  },
};

const DAY_MS = 86_400_000;

export function daysSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / DAY_MS));
}

export function ago(iso: string, now: Date = new Date()): string {
  const days = daysSince(iso, now);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "about a month ago" : `about ${months} months ago`;
}

/** Pages render on the server (UTC), so dates are pinned to the audience's timezone. */
export const TIME_ZONE = "America/Toronto";

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: TIME_ZONE,
  }).format(new Date(iso));
}

/** "Granite Payments' site", "Stripe's site". */
export function possessive(name: string): string {
  return /s$/i.test(name) ? `${name}'` : `${name}'s`;
}

export function formatMonthDay(isoDate: string): string {
  // Calendar dates are plain YYYY-MM-DD; parse as local noon so no timezone shifts the day.
  return new Intl.DateTimeFormat("en-CA", { month: "short", day: "numeric" }).format(
    new Date(`${isoDate}T12:00:00`),
  );
}

/** Pound and euro amounts carry their own symbol; dollar amounts name their currency at the end. */
const SYMBOLS: Record<string, string> = { GBP: "£", EUR: "€" };
const DOLLARS = new Set(["USD", "CAD", "AUD"]);
const PER = { hour: " an hour", month: " a month", year: " a year" } as const;

/**
 * Any other currency, the way its own readers write it: rupees in lakhs (₹30L),
 * others with their sign or code (SGD 200k, PLN 16,000, ₩230M). Yearly pay is
 * shortened; hourly and monthly pay is shown in full.
 */
function formatForeignSalary(salary: NonNullable<Job["salary"]>, code: string): string {
  const locale = code === "INR" ? "en-IN" : "en-CA";
  const money = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: code,
    ...(salary.period === "year"
      ? { notation: "compact", minimumFractionDigits: 0, maximumFractionDigits: 1 }
      : { minimumFractionDigits: 0, maximumFractionDigits: salary.period === "hour" ? 2 : 0 }),
  });
  const show = (value: number) => money.format(value).replace(/(\d)K\b/, "$1k");
  const range = salary.min === salary.max ? show(salary.min) : `${show(salary.min)} to ${show(salary.max)}`;
  return `${range}${PER[salary.period]}`;
}

export function formatSalary(salary: NonNullable<Job["salary"]>): string {
  const code = salary.currency ?? "";
  if (code && !DOLLARS.has(code) && !SYMBOLS[code]) {
    try {
      return formatForeignSalary(salary, code);
    } catch {
      // a code this browser doesn't know: fall through to the plain format, naming the code
    }
  }
  const symbol = SYMBOLS[code] ?? "$";
  const currency = symbol === "$" ? (salary.currency ?? "") : "";
  const hourly = salary.period === "hour";
  // hourly rates with cents show both digits ($25.50, $32.00); whole rates show none ($30)
  const cents = hourly && (salary.min % 1 !== 0 || salary.max % 1 !== 0) ? 2 : 0;
  const money = new Intl.NumberFormat("en-CA", { minimumFractionDigits: cents, maximumFractionDigits: cents });
  // yearly pay in thousands ($85k); hourly and monthly pay in full ($32, $6,500)
  const show = (value: number) =>
    salary.period === "year" ? `${symbol}${money.format(Math.round(value / 1000))}k` : `${symbol}${money.format(value)}`;
  const range = salary.min === salary.max ? show(salary.min) : `${show(salary.min)} to ${show(salary.max)}`;
  return `${range}${PER[salary.period]}${currency ? ` ${currency}` : ""}`;
}

export function pluralize(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString("en-CA")} ${count === 1 ? one : many}`;
}

/** "Toronto, ON" or "Toronto, ON +2 more" for a multi-city posting. */
export function shortLocation(location: string | null | undefined): string {
  if (!location) return "Location not listed";
  const places = location.split(" | ").filter(Boolean);
  return places.length > 1 ? `${places[0]} +${places.length - 1} more` : (places[0] ?? location);
}

export function allLocations(location: string | null | undefined): string[] {
  return (location ?? "").split(" | ").filter(Boolean);
}

/** A share as a whole percentage. A small but real share reads "<1%", never a misleading "0%". */
export function percent(part: number, whole: number): string {
  if (!whole || !part) return "0%";
  const value = Math.round((part / whole) * 100);
  return value === 0 ? "<1%" : `${value}%`;
}

/** Two letters for a company's fallback logo: "Granite Payments" -> "GP", "Stripe" -> "St". */
export function initials(name: string): string {
  const words = name.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  if (words.length >= 2) return `${words[0]![0]}${words[1]![0]}`.toUpperCase();
  const word = words[0] ?? name;
  return word.slice(0, 2).replace(/^./, (c) => c.toUpperCase());
}
