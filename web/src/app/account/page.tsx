import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { formatDate } from "@/lib/format";
import { currentUser } from "@/lib/session";

import { GitHubMark, GoogleMark } from "@/components/OAuthButtons";
import { api } from "@/lib/api";
import { oauthErrorMessage } from "@/lib/oauth";

import { DangerZone, NameForm, PasswordForm, SessionsForm, UnlinkProvider, VerifyNotice } from "./AccountForms";

const PROVIDER_INFO = {
  google: { label: "Google", mark: <GoogleMark /> },
  github: { label: "GitHub", mark: <GitHubMark /> },
} as const;

export const metadata: Metadata = { title: "Your account", robots: { index: false } };

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line py-8 md:grid-cols-[16rem_1fr] md:gap-10">
      <div>
        <h2 className="font-sans text-base font-semibold text-ink">{title}</h2>
        {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
      </div>
      <div className="max-w-lg">{children}</div>
    </section>
  );
}

export default async function AccountPage({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string; reset?: string; linked?: string; error?: string }>;
}) {
  const user = await currentUser();
  if (!user) redirect("/login?next=/account");
  const { welcome, reset, linked, error } = await searchParams;
  const enabled = await api.providers();
  const linkedNow = new Set(user.sign_in_providers ?? []);
  const providerRows = (["google", "github"] as const).filter((p) => enabled[p] || linkedNow.has(p));
  const hasPassword = user.has_password ?? true;
  const problem = oauthErrorMessage(error);

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <h1 className="text-4xl font-semibold text-ink">Your account</h1>
      <p className="mt-2 text-ink-soft">
        Signed in as <span className="font-medium text-ink">{user.email}</span>. Member since {formatDate(user.created_at)}.
      </p>

      {welcome && (
        <div className="mt-6 rounded-xl border border-accent/30 bg-accent-tint p-5">
          <p className="font-semibold text-ink">Welcome to Ghostless.</p>
          <p className="mt-1 text-sm text-ink-soft">
            Next: <Link href="/resume" className="font-medium text-accent hover:underline">upload your resume</Link> to see how you
            match every job, or <Link href="/jobs" className="font-medium text-accent hover:underline">start searching</Link>.
          </p>
        </div>
      )}
      {reset && <p className="mt-6 rounded-lg bg-good-tint px-4 py-3 text-sm text-good">Your password was changed and other devices were signed out.</p>}
      {linked && linked in PROVIDER_INFO && (
        <p className="mt-6 rounded-lg bg-good-tint px-4 py-3 text-sm text-good">
          {PROVIDER_INFO[linked as keyof typeof PROVIDER_INFO].label} is connected. You can now sign in with it.
        </p>
      )}
      {problem && <p role="alert" className="mt-6 rounded-lg bg-brick-tint px-4 py-3 text-sm text-brick">{problem}</p>}

      <div className="mt-8">
        <Section title="Profile" description="Your name is only shown to you.">
          <NameForm name={user.name ?? ""} />
        </Section>
        <Section title="Email" description="Used for password resets. Ghostless doesn't send marketing email.">
          <p className="text-ink">
            {user.email}{" "}
            {user.email_verified ? (
              <span className="ml-1 rounded-full bg-good-tint px-2 py-0.5 text-xs font-medium text-good">Confirmed</span>
            ) : (
              <span className="ml-1 rounded-full bg-ochre-tint px-2 py-0.5 text-xs font-medium text-ochre">Not confirmed</span>
            )}
          </p>
          {!user.email_verified && <VerifyNotice />}
        </Section>
        {providerRows.length > 0 && (
          <Section title="Sign-in methods" description="Ways to sign in besides your email and password.">
            <ul className="space-y-3">
              {providerRows.map((p) => (
                <li key={p} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface p-4">
                  <span className="flex items-center gap-3 font-medium text-ink">
                    {PROVIDER_INFO[p].mark}
                    {PROVIDER_INFO[p].label}
                    {linkedNow.has(p) && <span className="rounded-full bg-good-tint px-2 py-0.5 text-xs font-medium text-good">Connected</span>}
                  </span>
                  {linkedNow.has(p) ? (
                    <UnlinkProvider provider={p} label={PROVIDER_INFO[p].label} />
                  ) : (
                    <a
                      href={`/api/auth/oauth/${p}/start?link=1`}
                      className="inline-flex h-10 items-center rounded-lg border border-line-strong bg-surface px-4 text-sm font-medium text-ink hover:border-ink-faint"
                    >
                      Connect {PROVIDER_INFO[p].label}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}
        <Section title="Password">
          <PasswordForm hasPassword={hasPassword} />
        </Section>
        <Section title="Devices" description="Signed in somewhere you don't recognize? Sign out everywhere else.">
          <SessionsForm />
        </Section>
        <Section title="Your data" description="Everything Ghostless stores about you, as a file.">
          <a href="/api/me/export" className="inline-flex h-11 items-center rounded-lg border border-line-strong bg-surface px-5 font-medium text-ink hover:border-ink-faint">
            Download my data
          </a>
          <p className="mt-2 text-sm text-ink-soft">
            Includes your account, saved jobs, resumes, reports and recent activity. Read the{" "}
            <Link href="/privacy" className="text-accent hover:underline">privacy policy</Link> for how it&apos;s used.
          </p>
        </Section>
        <Section title="Delete account" description="Deletes your account, saved jobs and resumes for good.">
          <DangerZone hasPassword={hasPassword} />
        </Section>
      </div>
    </div>
  );
}
