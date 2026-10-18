import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DailyBars } from "@/components/DailyBars";
import { Stat } from "@/components/Stat";
import { api } from "@/lib/api";
import type { ReportRow } from "@/lib/api-types";
import { ago, formatDate, pluralize } from "@/lib/format";
import { visitorClient } from "@/lib/route";
import { currentUser } from "@/lib/session";

import { updateReport } from "./actions";

export const metadata: Metadata = { title: "Admin", robots: { index: false } };

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "users", label: "Users" },
  { key: "reports", label: "Reports" },
  { key: "errors", label: "Errors" },
  { key: "ingest", label: "Data pipeline" },
] as const;
type Tab = (typeof TABS)[number]["key"];

const REPORT_STATUSES: { value: ReportRow["status"]; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "dismissed", label: "Dismissed" },
];

const cell = "px-3 py-2.5 text-left align-top";
const head = "px-3 py-2 text-left text-xs font-semibold text-ink-soft";

function Table({ caption, children }: { caption: string; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[40rem] border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

type Props = { searchParams: Promise<{ tab?: string; q?: string; status?: string; page?: string }> };

export default async function AdminPage({ searchParams }: Props) {
  const user = await currentUser();
  // not a hint that the page exists: anyone but an admin gets a plain 404
  if (user?.role !== "admin") notFound();
  const params = await searchParams;
  const tab: Tab = TABS.some((t) => t.key === params.tab) ? (params.tab as Tab) : "overview";
  const c = await visitorClient();

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-semibold text-ink">Admin</h1>
          <p className="text-ink-soft">How people use Ghostless, what they report, and whether the data is fresh.</p>
        </div>
      </div>
      <nav aria-label="Admin sections" className="mb-8 border-b border-line">
        <ul className="-mb-px flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <li key={t.key}>
              <Link
                href={t.key === "overview" ? "/admin" : `/admin?tab=${t.key}`}
                aria-current={tab === t.key ? "page" : undefined}
                className="block border-b-2 border-transparent px-4 py-2.5 text-sm font-medium whitespace-nowrap text-ink-soft hover:text-ink aria-[current=page]:border-accent aria-[current=page]:text-ink"
              >
                {t.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {tab === "overview" && <Overview c={c} />}
      {tab === "users" && <Users c={c} q={params.q ?? ""} page={Math.max(1, Number(params.page) || 1)} />}
      {tab === "reports" && <Reports c={c} status={REPORT_STATUSES.find((s) => s.value === params.status)?.value} />}
      {tab === "errors" && <Errors c={c} />}
      {tab === "ingest" && <Ingest c={c} />}
    </div>
  );
}

type Client = Awaited<ReturnType<typeof visitorClient>>;

async function Overview({ c }: { c: Client }) {
  const [o, daily, pages] = await Promise.all([api.admin.overview(c), api.admin.daily(c, 30), api.admin.topPages(c, 7)]);
  const days = daily.map((d) => d.day);
  const lastRun = o.last_run as { started_at?: string; companies_failed?: number } | null;
  return (
    <div className="space-y-8">
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Accounts" value={o.users_total.toLocaleString("en-CA")} note={`${o.users_new_7d} new this week, ${o.users_verified} verified`} />
        <Stat label="Active users" value={o.users_active_7d.toLocaleString("en-CA")} note={`last 7 days; ${o.users_active_30d} in 30 days`} />
        <Stat label="Visitors today" value={o.visitors_today.toLocaleString("en-CA")} note={`${o.visitors_7d.toLocaleString("en-CA")} this week, ${o.pageviews_7d.toLocaleString("en-CA")} page views`} />
        <Stat label="Resume checks" value={o.analyses_7d.toLocaleString("en-CA")} note={`this week; ${o.resumes_stored} resumes stored, ${o.ai_feedback_7d} AI reviews`} />
        <Stat label="Saved jobs" value={o.saved_jobs.toLocaleString("en-CA")} note="across all accounts" />
        <Stat label="Open reports" value={o.reports_open.toLocaleString("en-CA")} note={<Link href="/admin?tab=reports" className="text-accent hover:underline">Review reports</Link>} tone={o.reports_open > 0 ? "warn" : undefined} />
        <Stat label="Errors, 24 hours" value={o.errors_24h.toLocaleString("en-CA")} note={<Link href="/admin?tab=errors" className="text-accent hover:underline">See errors</Link>} tone={o.errors_24h > 0 ? "warn" : undefined} />
        <Stat
          label="Open postings"
          value={o.jobs_active.toLocaleString("en-CA")}
          note={lastRun?.started_at ? `last run ${ago(lastRun.started_at)}${lastRun.companies_failed ? `, ${lastRun.companies_failed} failed` : ""}` : "no runs yet"}
          tone={lastRun?.companies_failed ? "warn" : undefined}
        />
      </dl>
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="sr-only">Visitors</h2>
          <DailyBars title="Visitors per day" days={days} values={daily.map((d) => d.visitors)} unit="visitors" />
        </section>
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="sr-only">Sign-ups</h2>
          <DailyBars title="Sign-ups per day" days={days} values={daily.map((d) => d.signups)} unit="sign-ups" />
        </section>
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="sr-only">Active users</h2>
          <DailyBars title="Signed-in users active per day" days={days} values={daily.map((d) => d.active_users)} unit="active users" />
        </section>
        <section className="rounded-2xl border border-line bg-surface p-5">
          <h2 className="sr-only">Resume checks</h2>
          <DailyBars title="Resume checks per day" days={days} values={daily.map((d) => d.analyses)} unit="checks" />
        </section>
      </div>
      <section>
        <h2 className="mb-3 text-xl font-semibold text-ink">Most viewed pages, last 7 days</h2>
        {pages.length ? (
          <Table caption="Most viewed pages">
            <thead>
              <tr className="border-b border-line bg-sunken">
                <th scope="col" className={head}>Page</th>
                <th scope="col" className={`${head} text-right`}>Views</th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr key={p.path} className="border-b border-line last:border-0">
                  <th scope="row" className={`${cell} font-normal text-ink`}>{p.path}</th>
                  <td className={`${cell} text-right`}>{p.views.toLocaleString("en-CA")}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <p className="text-sm text-ink-soft">No page views recorded yet.</p>
        )}
        <p className="mt-2 text-xs text-ink-faint">
          Counted without cookies or IP addresses: visitors are estimated from a daily salted hash, so they can&apos;t be tracked
          across days.
        </p>
      </section>
    </div>
  );
}

const PAGE = 50;

async function Users({ c, q, page }: { c: Client; q: string; page: number }) {
  const result = await api.admin.users(c, { q: q || undefined, limit: PAGE, offset: (page - 1) * PAGE });
  const pages = Math.max(1, Math.ceil(result.total / PAGE));
  const link = (p: number) => `/admin?tab=users${q ? `&q=${encodeURIComponent(q)}` : ""}${p > 1 ? `&page=${p}` : ""}`;
  return (
    <div className="space-y-4">
      <form action="/admin" method="get" className="flex max-w-md gap-2">
        <input type="hidden" name="tab" value="users" />
        <label htmlFor="admin-q" className="sr-only">Search by email or name</label>
        <input id="admin-q" name="q" defaultValue={q} placeholder="Search by email or name" className="h-10 min-w-0 flex-1 rounded-lg border border-line-strong bg-surface px-3 text-ink" />
        <button className="h-10 rounded-lg bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover">Search</button>
      </form>
      <p className="text-sm text-ink-soft">{pluralize(result.total, "account")}</p>
      <Table caption="Accounts">
        <thead>
          <tr className="border-b border-line bg-sunken">
            <th scope="col" className={head}>Email</th>
            <th scope="col" className={head}>Name</th>
            <th scope="col" className={head}>Joined</th>
            <th scope="col" className={head}>Last active</th>
            <th scope="col" className={`${head} text-right`}>Saved</th>
            <th scope="col" className={`${head} text-right`}>Resumes</th>
          </tr>
        </thead>
        <tbody>
          {result.items.map((u) => (
            <tr key={u.id} className="border-b border-line last:border-0">
              <th scope="row" className={`${cell} font-medium text-ink`}>
                {u.email}
                {u.role === "admin" && <span className="ml-2 rounded-full bg-accent-tint px-2 py-0.5 text-xs text-accent">admin</span>}
                {!u.email_verified && <span className="ml-2 text-xs font-normal text-ink-faint">unverified</span>}
              </th>
              <td className={cell}>{u.name ?? <span className="text-ink-faint">None</span>}</td>
              <td className={cell}>{formatDate(u.created_at)}</td>
              <td className={cell}>{u.last_active_at ? ago(u.last_active_at) : <span className="text-ink-faint">Never</span>}</td>
              <td className={`${cell} text-right`}>{u.saved_jobs}</td>
              <td className={`${cell} text-right`}>{u.resumes}</td>
            </tr>
          ))}
        </tbody>
      </Table>
      {pages > 1 && (
        <nav aria-label="Pages" className="flex items-center justify-between text-sm">
          {page > 1 ? <Link href={link(page - 1)} className="text-accent hover:underline">Previous</Link> : <span />}
          <span className="text-ink-soft">Page {page} of {pages}</span>
          {page < pages ? <Link href={link(page + 1)} className="text-accent hover:underline">Next</Link> : <span />}
        </nav>
      )}
    </div>
  );
}

async function Reports({ c, status }: { c: Client; status?: ReportRow["status"] }) {
  const reports = await api.admin.reports(c, status);
  return (
    <div className="space-y-4">
      <ul className="flex flex-wrap gap-2 text-sm">
        {[{ value: undefined, label: "All" }, ...REPORT_STATUSES].map((s) => (
          <li key={s.label}>
            <Link
              href={`/admin?tab=reports${s.value ? `&status=${s.value}` : ""}`}
              aria-current={status === s.value ? "true" : undefined}
              className="inline-block rounded-full border border-line-strong bg-surface px-3.5 py-1.5 font-medium text-ink hover:border-ink-faint aria-[current=true]:border-accent aria-[current=true]:bg-accent-tint aria-[current=true]:text-accent"
            >
              {s.label}
            </Link>
          </li>
        ))}
      </ul>
      {reports.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line-strong p-6 text-sm text-ink-soft">No reports here.</p>
      ) : (
        <ul className="space-y-3">
          {reports.map((r) => (
            <li key={r.id} className="rounded-xl border border-line bg-surface p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold text-ink">
                  {r.category.replaceAll("_", " ")}
                  <span className="font-normal text-ink-faint"> #{r.id}, {ago(r.created_at)}</span>
                </p>
                <p className="text-sm text-ink-soft">
                  {r.email ?? (r.user_id ? `user ${r.user_id}` : "anonymous")}
                </p>
              </div>
              {(r.job_id || r.page) && (
                <p className="mt-1 text-sm text-ink-soft">
                  {r.job_id ? (
                    <Link href={`/jobs/${r.job_id}`} className="text-accent hover:underline">{r.job_title ?? `Job ${r.job_id}`}</Link>
                  ) : (
                    r.page
                  )}
                </p>
              )}
              <p className="mt-3 whitespace-pre-line text-ink">{r.message}</p>
              <form action={updateReport} className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4">
                <input type="hidden" name="id" value={r.id} />
                <label className="text-sm text-ink-soft">
                  <span className="mb-1 block">Status</span>
                  <select name="status" defaultValue={r.status} className="h-9 rounded-lg border border-line-strong bg-surface px-2 text-ink">
                    {REPORT_STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </label>
                <label className="min-w-0 flex-1 text-sm text-ink-soft">
                  <span className="mb-1 block">Note (private)</span>
                  <input name="admin_note" defaultValue={r.admin_note ?? ""} maxLength={2000} className="h-9 w-full rounded-lg border border-line-strong bg-surface px-3 text-ink" />
                </label>
                <button className="h-9 rounded-lg bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-hover">Update</button>
              </form>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

async function Errors({ c }: { c: Client }) {
  const errors = await api.admin.errors(c);
  if (!errors.length) return <p className="rounded-xl border border-dashed border-line-strong p-6 text-sm text-ink-soft">No errors reported. Pages that crash in visitors&apos; browsers show up here.</p>;
  return (
    <Table caption="Recent errors">
      <thead>
        <tr className="border-b border-line bg-sunken">
          <th scope="col" className={head}>When</th>
          <th scope="col" className={head}>Page</th>
          <th scope="col" className={head}>Message</th>
          <th scope="col" className={head}>Digest</th>
        </tr>
      </thead>
      <tbody>
        {errors.map((e) => (
          <tr key={e.id} className="border-b border-line last:border-0">
            <td className={`${cell} whitespace-nowrap`}>{ago(e.created_at)}</td>
            <td className={cell}>{e.path ?? ""}</td>
            <td className={`${cell} text-ink`}>{e.message ?? ""}</td>
            <td className={`${cell} text-ink-faint`}>{e.digest ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

async function Ingest({ c }: { c: Client }) {
  const runs = await api.admin.runs(c);
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-soft">The daily run that collects postings. A run with failed companies needs a look at the GitHub Actions log.</p>
      <Table caption="Recent ingest runs">
        <thead>
          <tr className="border-b border-line bg-sunken">
            <th scope="col" className={head}>Started</th>
            <th scope="col" className={`${head} text-right`}>Companies OK</th>
            <th scope="col" className={`${head} text-right`}>Failed</th>
            <th scope="col" className={`${head} text-right`}>Seen</th>
            <th scope="col" className={`${head} text-right`}>New</th>
            <th scope="col" className={`${head} text-right`}>Closed</th>
            <th scope="col" className={`${head} text-right`}>Minutes</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.started_at} className="border-b border-line last:border-0">
              <th scope="row" className={`${cell} font-normal text-ink`}>
                {formatDate(r.started_at)}
                {!r.finished_at && <span className="ml-2 text-xs text-ochre">running or stopped</span>}
              </th>
              <td className={`${cell} text-right`}>{r.companies_ok}</td>
              <td className={`${cell} text-right ${r.companies_failed ? "font-semibold text-brick" : ""}`}>{r.companies_failed}</td>
              <td className={`${cell} text-right`}>{r.jobs_seen.toLocaleString("en-CA")}</td>
              <td className={`${cell} text-right`}>{r.jobs_new.toLocaleString("en-CA")}</td>
              <td className={`${cell} text-right`}>{r.jobs_closed.toLocaleString("en-CA")}</td>
              <td className={`${cell} text-right`}>{r.duration_seconds ? Math.round(r.duration_seconds / 60) : ""}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}
