# Ghostless web

The website for Ghostless: job search with true posting ages, ghost signals, a skills gap tool and a hiring calendar. Built with Next.js (App Router), TypeScript and Tailwind CSS, reading the [Ghostless API](../README.md#web-api).

## Run it locally

You need Node.js 20.19+ (22 LTS recommended) and the API running.

```bash
# terminal 1, repo root: demo data and the API
pip install -e ".[dev]"
python scripts/seed_demo.py --yes      # fictional companies, 90 days of history
ghostless serve                        # http://127.0.0.1:8000

# terminal 2
cd web
cp .env.example .env.local
npm install
npm run dev                            # http://localhost:3000
```

To use your real data instead, skip the seed script and point `DATABASE_URL` at your Neon database.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` / `npm start` | Production build and server |
| `npm run lint` | ESLint (Next.js rules, accessibility, TypeScript) |
| `npm run typecheck` | TypeScript, strict mode |
| `npm run test:e2e` | Playwright: unit tests for filters and formatting, plus the main user journeys on desktop and mobile |
| `npm run gen:api` | Regenerates `src/lib/api-schema.d.ts` from the running API |

## How it's built

```
src/
  app/                 routes: /, /jobs, /jobs/[id], /companies, /companies/[slug], /skills,
                       /calendar, /resume, /resume/builder, /resume/matches, /saved, /settings,
                       /account, /login, /signup, /admin, /privacy, /terms, /how-it-works
    api/               the site's own routes: saved jobs, resumes, settings, reports, analytics
  components/          JobCard, JobDetailParts, FilterBar, AgeStrip, RiskBadge, WeeklyChart,
                       CompanyLogo, SaveButton, ...
  lib/
    api.ts             typed API client (server-only)
    api-schema.d.ts    generated from the API's OpenAPI spec, never edited by hand
    filters.ts         job search filters <-> URL, shared by server and client
    format.ts          labels, dates, salaries
    session.ts         the session cookie and the signed-in user (server-only)
    prefs.ts           display settings, shared by server and browser
    saved.ts           saved jobs: in the browser when signed out, on the account when signed in
    resume.ts          the resume used for match scores
tests/                 Playwright specs
```

- **Server-rendered.** Pages fetch from the API on the server, so they load fast, work without JavaScript, and are readable by search engines. API responses are cached for five minutes, since data changes once a day.
- **The API URL never reaches browsers.** `src/lib/api.ts` is marked `server-only`, so importing it from client code fails the build.
- **Typed end to end.** `api-schema.d.ts` is generated from the API, and CI fails if it's out of date, so an API change shows up as a type error instead of a broken page.
- **Filters live in the URL.** Every search, and the job open in the preview pane (`?job=`), is shareable and bookmarkable. The filter dropdowns are `<details>` elements in a plain GET form, so they work without JavaScript; a small client component adds instant updates. Invalid parameters are dropped, never turned into an error page. With no role chosen, searches cover tech roles only.
- **Split view on desktop, pages on phones.** On wide screens a result opens in the preview pane without losing your place in the list; on phones, or with a modified click, it opens the job's own page.
- **Evidence, not just flags.** The job record quotes the sentence each disclosure and the "not a real opening" flag came from, so users can check the call themselves.
- **Logos without tracking.** Company logos come from Google's favicon service through Next's image optimizer, so visitors' browsers never contact Google; companies without a known domain get a lettered tile.
- **Accessible by default.** Risk is shown by colour, shape and text together; chart bars use solid versus hollow fills plus a text column; there's a skip link, visible focus states, and a check that no page scrolls sideways on a phone.
- **Real 404s.** Unknown jobs return HTTP 404, so search engines don't index empty pages.

## Design

Warm neutral surfaces with one blue accent for actions and links. Colour is kept for meaning: the risk scale (no flags neutral, some flags ochre, high risk brick), errors (a separate danger colour) and charts. Inter for all text, self-hosted. Dark mode is layered warm greys, not an inversion, and every text colour passes WCAG AA in both themes. Every chart has a legend and a table of its numbers. The design is summarised in [DESIGN.md](DESIGN.md).

Colours are CSS variables in `src/app/globals.css`. Display settings (theme, text size, density, motion, underlined links) are attributes on `<html>`, set by the server from a cookie or the account, so pages render right the first time with no flash. The signature element is the age strip in `src/components/AgeStrip.tsx`: how long a posting has really been open, against how long the employer usually takes.

## Accounts and sessions

The API owns accounts. At sign-in it returns a session token, which the website keeps in an httpOnly, SameSite=Lax cookie, so page scripts can never read it. The website calls the API from its server with that token (`src/lib/session.ts`, `src/lib/route.ts`). Its own `/api/*` routes accept requests only from this site's pages.

The website forwards each visitor's IP address to the API with a shared secret (`GHOSTLESS_INTERNAL_KEY`), so rate limits and visitor counts apply per visitor rather than to the website's server.

Saved jobs and resume checks work without an account too, kept in the browser. Saved jobs move to the account at sign-in.

## Deploying

On Vercel: import the repo, set the root directory to `web`, and set:

- `GHOSTLESS_API_URL`: the deployed API
- `NEXT_PUBLIC_SITE_URL`: this site's URL
- `GHOSTLESS_INTERNAL_KEY`: the same secret as the API's

See the root README for the API's settings.

## Planned: the browser extension

Reuse `api-schema.d.ts` and the request layer in `src/lib/api.ts` for a typed client, so the extension can show a posting's ghost signals and your match score on employer career pages. Its origin goes in the API's `GHOSTLESS_CORS_ORIGINS`.
