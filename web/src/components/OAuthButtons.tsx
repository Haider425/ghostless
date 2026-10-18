import type { ReactNode } from "react";

/*
  "Continue with Google / GitHub". Plain links to the start route, so they
  work without JavaScript. Only providers the API has turned on are shown;
  with none, nothing renders.
*/

function GoogleMark() {
  // Google's "G", as its sign-in branding guidelines ask for
  return (
    <svg viewBox="0 0 18 18" className="size-[18px]" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
    </svg>
  );
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" className="size-[18px]" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

const PROVIDERS = [
  { id: "google", label: "Google", mark: <GoogleMark /> },
  { id: "github", label: "GitHub", mark: <GitHubMark /> },
] as const;

export function OAuthButtons({
  enabled,
  next = "/",
  note,
}: {
  enabled: { google: boolean; github: boolean };
  next?: string;
  note?: ReactNode;
}) {
  const shown = PROVIDERS.filter((p) => enabled[p.id]);
  if (!shown.length) return null;
  const query = next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
  return (
    <div className="space-y-3">
      <div className="grid gap-2.5">
        {shown.map((p) => (
          <a
            key={p.id}
            href={`/api/auth/oauth/${p.id}/start${query}`}
            className="inline-flex h-11 items-center justify-center gap-2.5 rounded-lg border border-line-strong bg-surface px-4 font-medium text-ink transition-colors hover:border-ink-faint hover:bg-sunken"
          >
            {p.mark}
            Continue with {p.label}
          </a>
        ))}
      </div>
      {note && <p className="text-center text-xs text-ink-faint">{note}</p>}
      <div className="flex items-center gap-3 text-sm text-ink-faint" aria-hidden="true">
        <span className="h-px flex-1 bg-line" />
        or with email
        <span className="h-px flex-1 bg-line" />
      </div>
    </div>
  );
}

export { GitHubMark, GoogleMark };
