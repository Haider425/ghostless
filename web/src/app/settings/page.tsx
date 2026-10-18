import type { Metadata } from "next";

import { currentPrefs, currentUser } from "@/lib/session";

import { SettingsForm } from "./SettingsForm";

export const metadata: Metadata = { title: "Settings", robots: { index: false } };

export default async function SettingsPage() {
  const [prefs, user] = await Promise.all([currentPrefs(), currentUser()]);
  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="text-4xl font-semibold text-ink">Settings</h1>
      <p className="mt-2 text-ink-soft">
        {user
          ? "Saved to your account, so they follow you to every device."
          : "Saved in this browser. Sign in to keep them on every device."}{" "}
        Changes apply right away.
      </p>
      <SettingsForm initial={prefs} />
    </div>
  );
}
