"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { type Prefs, htmlAttributes } from "@/lib/prefs";

/** Apply preferences to <html> immediately, the same way the server does on page load. */
function applyToPage(prefs: Prefs) {
  const root = document.documentElement;
  for (const [name, value] of Object.entries(htmlAttributes(prefs))) {
    if (value === undefined) root.removeAttribute(name);
    else root.setAttribute(name, value);
  }
}

function Group({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line py-8 md:grid-cols-[16rem_1fr] md:gap-10">
      <div>
        <h2 className="font-sans text-base font-semibold text-ink">{title}</h2>
        {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
      </div>
      <div className="space-y-6">{children}</div>
    </section>
  );
}

function Choice<T extends string>({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: T;
  options: { value: T; label: string; preview?: ReactNode }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-ink">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex min-w-[6.5rem] cursor-pointer items-center gap-2 rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-sm text-ink transition-colors hover:border-ink-faint has-[:checked]:border-accent has-[:checked]:bg-accent-tint has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--focus)]"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.preview}
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Toggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-6">
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="block text-sm text-ink-soft">{description}</span>
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
        <span className="h-6 w-11 rounded-full bg-line-strong transition-colors peer-checked:bg-accent-solid peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[var(--focus)]" />
        <span className="absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  );
}

const SWATCH = "inline-block size-4 rounded-full border border-line-strong";

export function SettingsForm({ initial }: { initial: Prefs }) {
  const [prefs, setPrefs] = useState<Prefs>(initial);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const router = useRouter();
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    applyToPage(prefs);
    setStatus("saving");
    const timer = setTimeout(async () => {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(prefs),
      }).catch(() => null);
      setStatus(response?.ok ? "saved" : "error");
      if (response?.ok) router.refresh(); // so links that depend on settings update
    }, 350);
    return () => clearTimeout(timer);
  }, [prefs, router]);

  const set = <K extends keyof Prefs>(key: K) => (value: Prefs[K]) => setPrefs((p) => ({ ...p, [key]: value }));

  return (
    <div className="mt-8">
      <p aria-live="polite" className="sticky top-16 z-10 mb-2 h-6 text-right text-sm text-ink-soft">
        {status === "saving" ? "Saving..." : status === "saved" ? "Saved" : status === "error" ? "Couldn't save. Check your connection." : ""}
      </p>

      <Group title="Appearance" description="How Ghostless looks on this device and your others.">
        <Choice
          legend="Theme"
          name="theme"
          value={prefs.theme}
          onChange={set("theme")}
          options={[
            { value: "system", label: "Match my device", preview: <span className={`${SWATCH} bg-gradient-to-r from-white from-50% to-[#15181e] to-50%`} /> },
            { value: "light", label: "Light", preview: <span className={`${SWATCH} bg-white`} /> },
            { value: "dark", label: "Dark", preview: <span className={`${SWATCH} bg-[#15181e]`} /> },
          ]}
        />
        <Choice
          legend="Text size"
          name="text_size"
          value={prefs.text_size}
          onChange={set("text_size")}
          options={[
            { value: "sm", label: "Small" },
            { value: "md", label: "Default" },
            { value: "lg", label: "Large" },
            { value: "xl", label: "Extra large" },
          ]}
        />
        <Choice
          legend="Job list density"
          name="density"
          value={prefs.density}
          onChange={set("density")}
          options={[
            { value: "comfortable", label: "Comfortable" },
            { value: "compact", label: "Compact" },
          ]}
        />
        <Toggle label="Reduce motion" description="Turn off animations and transitions." checked={prefs.reduce_motion} onChange={set("reduce_motion")} />
        <Toggle label="Underline links" description="Makes links easier to spot in text." checked={prefs.underline_links} onChange={set("underline_links")} />
      </Group>

      <Group title="Job search" description="Where a new search starts. You can still change filters any time.">
        <Choice
          legend="Default location"
          name="default_location"
          value={prefs.default_location}
          onChange={set("default_location")}
          options={[
            { value: "any", label: "Anywhere" },
            { value: "canada", label: "In Canada" },
            { value: "remote", label: "Remote" },
            { value: "canada_or_remote", label: "Canada or remote" },
          ]}
        />
        <Toggle
          label="Hide high ghost risk postings"
          description="Start searches without postings that have two or more ghost signals."
          checked={prefs.hide_high_risk}
          onChange={set("hide_high_risk")}
        />
      </Group>

      <Group title="Privacy">
        <Toggle
          label="Share anonymous usage stats"
          description="Counts page views without cookies or tracking you across days, so we know which features help. Browsers set to Do Not Track are never counted."
          checked={prefs.analytics}
          onChange={set("analytics")}
        />
      </Group>
    </div>
  );
}
