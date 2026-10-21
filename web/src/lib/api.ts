import "server-only";

import createClient, { type Client } from "openapi-fetch";

import type { components, paths } from "./api-schema";

/*
  Typed client for the Ghostless API. Types come from the API's OpenAPI spec
  (`npm run gen:api`), so a renamed field or endpoint fails the type check
  instead of breaking a page. Server-only: the API URL and session tokens
  never reach browsers.

  Two clients:
   - public: job data, cached for five minutes (it changes once a day)
   - authed: a visitor's own data, never cached
*/

export type * from "./api-types";
import type {
  CalendarQuery,
  CompanyListQuery,
  CompanyNamesQuery,
  GapQuery,
  JobQuery,
  OAuthProvider,
  Profile,
  ReportRow,
  Settings,
  SkillQuery,
} from "./api-types";

type Schemas = components["schemas"];

/** Data refreshes once a day, so pages can safely reuse responses for 5 minutes. */
const REVALIDATE_SECONDS = 300;
export const API_URL = process.env.GHOSTLESS_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApiError";
  }
}

type ApiClient = Client<paths>;

const publicClient: ApiClient = createClient<paths>({
  baseUrl: API_URL,
  fetch: (request: Request) => fetch(request, { next: { revalidate: REVALIDATE_SECONDS } }),
  querySerializer: { array: { style: "form", explode: true } },
});

/** A client for one visitor's requests: their session token and identity headers, never cached. */
export function authedClient(token: string | undefined, extraHeaders: Record<string, string> = {}): ApiClient {
  return createClient<paths>({
    baseUrl: API_URL,
    headers: { ...extraHeaders, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    fetch: (request: Request) => fetch(request, { cache: "no-store" }),
    querySerializer: { array: { style: "form", explode: true } },
  });
}

function detailOf(error: unknown, status: number, what: string): string {
  if (typeof error === "object" && error && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
      return String((detail[0] as { msg: unknown }).msg).replace(/^Value error, /, "");
    }
  }
  return `The API returned ${status} while loading ${what}.`;
}

async function call<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>, what: string): Promise<T> {
  let result;
  try {
    result = await promise;
  } catch (cause) {
    throw new ApiError(`Could not reach the Ghostless API while loading ${what}.`, 0, { cause });
  }
  const { data, error, response } = result;
  if (error !== undefined || data === undefined) {
    throw new ApiError(detailOf(error, response.status, what), response.status);
  }
  return data;
}

/** For endpoints that answer 204 No Content. */
async function callEmpty(promise: Promise<{ error?: unknown; response: Response }>, what: string): Promise<null> {
  let result;
  try {
    result = await promise;
  } catch (cause) {
    throw new ApiError(`Could not reach the Ghostless API while loading ${what}.`, 0, { cause });
  }
  if (!result.response.ok) throw new ApiError(detailOf(result.error, result.response.status, what), result.response.status);
  return null;
}

async function orNull<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 401)) return null;
    throw error;
  }
}

/** For form actions: a result with a message to show instead of a thrown error. */
export type Result<T> = { ok: true; data: T } | { ok: false; status: number; message: string };

export async function attempt<T>(promise: Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, data: await promise };
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, status: error.status, message: error.message };
    throw error;
  }
}

export const api = {
  // ---------- public job data ----------
  stats: () => call(publicClient.GET("/stats"), "stats"),
  jobs: (query: JobQuery) => call(publicClient.GET("/jobs", { params: { query } }), "jobs"),
  job: (id: number) =>
    orNull(call(publicClient.GET("/jobs/{job_id}", { params: { path: { job_id: id } } }), "the job")),
  terms: () => call(publicClient.GET("/terms"), "seasons"),
  companies: () => call(publicClient.GET("/companies"), "companies"),
  /** One page of the Companies page, searched and sorted by the API (only that page is read). */
  companyList: (query: CompanyListQuery) => call(publicClient.GET("/company-list", { params: { query } }), "companies"),
  /** Names and slugs only: every employer (sitemap), or the hiring ones matching `q` (suggestions). */
  companyNames: (query: CompanyNamesQuery = {}) => call(publicClient.GET("/company-names", { params: { query } }), "companies"),
  company: (slug: string) =>
    orNull(call(publicClient.GET("/companies/{slug}", { params: { path: { slug } } }), "the company")),
  weekly: (weeks = 12) => call(publicClient.GET("/trends/weekly", { params: { query: { weeks } } }), "weekly trends"),
  topSkills: (query: SkillQuery) => call(publicClient.GET("/skills/top", { params: { query } }), "skills"),
  gap: (query: GapQuery) => call(publicClient.GET("/skills/gap", { params: { query } }), "your skills gap"),
  calendar: (query: CalendarQuery) => call(publicClient.GET("/calendar", { params: { query } }), "the hiring calendar"),

  // ---------- accounts (pass an authed client) ----------
  me: (c: ApiClient) => orNull(call(c.GET("/me"), "your account")),
  signup: (c: ApiClient, body: { email: string; password: string; name?: string | null }) =>
    call(c.POST("/auth/signup", { body }), "sign-up"),
  login: (c: ApiClient, body: { email: string; password: string }) => call(c.POST("/auth/login", { body }), "sign-in"),
  /** Which Google and GitHub sign-ins are on (cached; both off if the API can't say). */
  providers: () =>
    call(publicClient.GET("/auth/providers"), "sign-in options").catch(() => ({ google: false, github: false })),
  oauthAuthorize: (c: ApiClient, provider: OAuthProvider, query: { redirect_uri: string; state: string; code_challenge: string }) =>
    call(c.GET("/auth/oauth/{provider}/authorize", { params: { path: { provider }, query } }), "sign-in"),
  oauthFinish: (c: ApiClient, provider: OAuthProvider, body: { code: string; redirect_uri: string; code_verifier: string }) =>
    call(c.POST("/auth/oauth/{provider}", { params: { path: { provider } }, body }), "sign-in"),
  unlinkProvider: (c: ApiClient, provider: OAuthProvider) =>
    call(c.DELETE("/me/oauth/{provider}", { params: { path: { provider } } }), "sign-in methods"),
  logout: (c: ApiClient) => c.POST("/auth/logout").catch(() => undefined),
  logoutEverywhere: (c: ApiClient) => call(c.POST("/auth/logout-everywhere"), "sign-out"),
  verifyEmail: (c: ApiClient, token: string) => call(c.POST("/auth/verify-email", { body: { token } }), "verification"),
  resendVerification: (c: ApiClient) => call(c.POST("/auth/resend-verification"), "verification"),
  forgotPassword: (c: ApiClient, email: string) =>
    call(c.POST("/auth/forgot-password", { body: { email } }), "the reset link"),
  resetPassword: (c: ApiClient, token: string, password: string) =>
    call(c.POST("/auth/reset-password", { body: { token, password } }), "the password reset"),
  updateProfile: (c: ApiClient, name: string | null) => call(c.PATCH("/me", { body: { name } }), "your profile"),
  saveSettings: (c: ApiClient, body: Settings) => call(c.PUT("/me/settings", { body }), "your settings"),
  changePassword: (c: ApiClient, current_password: string, new_password: string) =>
    call(c.POST("/me/password", { body: { current_password, new_password } }), "your password"),
  exportData: (c: ApiClient) => call(c.GET("/me/export"), "your data"),
  deleteAccount: (c: ApiClient, password: string) =>
    callEmpty(c.DELETE("/me", { body: { password } }), "account deletion"),
  savedJobs: (c: ApiClient) => call(c.GET("/me/saved"), "saved jobs"),
  savedIds: (c: ApiClient) => call(c.GET("/me/saved/ids"), "saved jobs"),
  updateSaved: (c: ApiClient, job_id: number, body: Schemas["SavedUpdateIn"]) =>
    call(c.PATCH("/me/saved/{job_id}", { params: { path: { job_id } }, body }), "your application"),
  saveJobs: (c: ApiClient, job_ids: number[]) => call(c.POST("/me/saved", { body: { job_ids } }), "saved jobs"),
  recordApplication: (c: ApiClient, job_id: number, source: Schemas["ApplicationIn"]["source"]) =>
    call(c.POST("/me/applications/{job_id}", { params: { path: { job_id } }, body: { source } }), "your application"),
  unsaveJob: (c: ApiClient, job_id: number) =>
    call(c.DELETE("/me/saved/{job_id}", { params: { path: { job_id } } }), "saved jobs"),

  // ---------- resumes ----------
  analyzeText: (c: ApiClient, text: string) => call(c.POST("/resume/analyze-text", { body: { text } }), "the analysis"),
  match: (c: ApiClient, body: { profile?: Profile | null; resume_id?: number | null; job_ids: number[] }) =>
    call(c.POST("/resume/match", { body }), "match scores"),
  recommendations: (c: ApiClient, body: Schemas["RecommendationsIn"]) =>
    call(c.POST("/resume/recommendations", { body }), "recommendations"),
  resumes: (c: ApiClient) => call(c.GET("/me/resumes"), "your resumes"),
  resume: (c: ApiClient, id: number) =>
    orNull(call(c.GET("/me/resumes/{resume_id}", { params: { path: { resume_id: id } } }), "the resume")),
  createResume: (c: ApiClient, body: Schemas["BuiltIn"]) => call(c.POST("/me/resumes", { body }), "the resume"),
  resumeAsDocument: (c: ApiClient, id: number) =>
    orNull(call(c.GET("/me/resumes/{resume_id}/as-document", { params: { path: { resume_id: id } } }), "the resume")),
  tailor: (c: ApiClient, body: Schemas["TailorIn"]) => call(c.POST("/resume/tailor", { body }), "the score"),
  importResume: (c: ApiClient, body: Schemas["ImportIn"]) => call(c.POST("/me/resumes/import", { body }), "the resume"),
  updateResume: (c: ApiClient, id: number, body: Schemas["BuiltIn"]) =>
    call(c.PUT("/me/resumes/{resume_id}", { params: { path: { resume_id: id } }, body }), "the resume"),
  primaryResume: (c: ApiClient, id: number) =>
    call(c.POST("/me/resumes/{resume_id}/primary", { params: { path: { resume_id: id } } }), "your resumes"),
  deleteResume: (c: ApiClient, id: number) =>
    call(c.DELETE("/me/resumes/{resume_id}", { params: { path: { resume_id: id } } }), "your resumes"),
  aiStatus: (c: ApiClient) => call(c.GET("/resume/ai-status"), "AI status"),
  /** Whether the site has AI feedback turned on (cached, no account needed). */
  aiEnabled: () =>
    call(publicClient.GET("/resume/ai-status"), "AI status").then(
      (s) => s.enabled,
      () => false,
    ),
  aiFeedback: (c: ApiClient, body: Schemas["AIIn"]) => call(c.POST("/resume/ai-feedback", { body }), "AI feedback"),

  // ---------- reports and analytics ----------
  report: (c: ApiClient, body: Schemas["ReportIn"]) => call(c.POST("/reports", { body }), "your report"),
  event: (c: ApiClient, body: Schemas["EventIn"]) => c.POST("/events", { body }).catch(() => undefined),

  // ---------- admin ----------
  admin: {
    overview: (c: ApiClient) => call(c.GET("/admin/overview"), "the overview"),
    daily: (c: ApiClient, days = 30) => call(c.GET("/admin/daily", { params: { query: { days } } }), "daily stats"),
    topPages: (c: ApiClient, days = 7) => call(c.GET("/admin/top-pages", { params: { query: { days } } }), "top pages"),
    users: (c: ApiClient, query: { q?: string; limit?: number; offset?: number }) =>
      call(c.GET("/admin/users", { params: { query } }), "users"),
    reports: (c: ApiClient, status?: ReportRow["status"]) =>
      call(c.GET("/admin/reports", { params: { query: status ? { status } : {} } }), "reports"),
    updateReport: (c: ApiClient, id: number, body: Schemas["ReportUpdate"]) =>
      call(c.PATCH("/admin/reports/{report_id}", { params: { path: { report_id: id } }, body }), "the report"),
    errors: (c: ApiClient) => call(c.GET("/admin/errors"), "errors"),
    runs: (c: ApiClient) => call(c.GET("/admin/runs"), "ingest runs"),
  },
};
