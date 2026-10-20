import type { Metadata } from "next";

import { SkillBars } from "@/components/SkillBars";
import { type Level, type RoleType, api } from "@/lib/api";
import { LEVELS, TECH_ROLES, type SearchParams } from "@/lib/filters";
import { LEVEL_LABELS, ROLE_LABELS, pluralize } from "@/lib/format";

export const metadata: Metadata = {
  title: "Skills gap",
  description: "Compare your skills with what current tech internship and new grad postings ask for.",
};

type Props = { searchParams: Promise<SearchParams> };

function list(value: string | string[] | undefined): string[] {
  return value === undefined ? [] : Array.isArray(value) ? value : [value];
}

export default async function SkillsPage({ searchParams }: Props) {
  const params = await searchParams;
  const have = (Array.isArray(params.have) ? params.have[0] : params.have)?.slice(0, 500).trim() ?? "";
  const roles = list(params.role).filter((r): r is RoleType => (TECH_ROLES as readonly string[]).includes(r));
  const levels = list(params.level).filter((l): l is Level => (LEVELS as readonly string[]).includes(l));
  const anywhere = params.anywhere === "1";
  const role = roles.length ? roles : (["sde"] as RoleType[]);
  const level = levels.length ? levels : (["intern", "new_grad"] as Level[]);

  const [gap, top] = await Promise.all([
    have ? api.gap({ have, role, level, anywhere, limit: 20 }) : Promise.resolve(null),
    have ? Promise.resolve(null) : api.topSkills({ role, level, anywhere, limit: 20 }),
  ]);
  const skills = gap?.skills ?? top ?? [];
  const total = gap?.total_postings;
  const topTen = gap ? gap.skills.slice(0, 10) : [];
  const haveCount = topTen.filter((s) => s.have).length;

  return (
    <div className="mx-auto max-w-[80rem] px-4 pt-10 pb-20 sm:px-6 lg:px-20">
      <div className="mb-8 max-w-2xl space-y-2">
        <h1 className="page-title">Skills gap</h1>
        <p className="page-lead">
          See which skills open postings ask for most, and which of them you&apos;re missing. Counts come from the
          descriptions of postings that are open right now.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[20rem_1fr]">
        <form action="/skills" method="get" className="space-y-5 self-start card p-6">
          <div className="space-y-1.5">
            <label htmlFor="have" className="text-sm font-semibold text-ink">
              Your skills
            </label>
            <textarea
              id="have"
              name="have"
              rows={3}
              maxLength={500}
              defaultValue={have}
              placeholder="Python, SQL, React, C#"
              className="field py-2"
            />
            <p className="text-xs text-ink-faint">Separate skills with commas.</p>
          </div>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-semibold text-ink">Role</legend>
            {TECH_ROLES.map((r) => (
              <label key={r} className="flex items-center gap-2.5 text-sm text-ink-soft">
                <input type="checkbox" name="role" value={r} defaultChecked={role.includes(r)} className="size-4 accent-[var(--accent)]" />
                {ROLE_LABELS[r]}
              </label>
            ))}
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-semibold text-ink">Level</legend>
            {LEVELS.map((l) => (
              <label key={l} className="flex items-center gap-2.5 text-sm text-ink-soft">
                <input type="checkbox" name="level" value={l} defaultChecked={level.includes(l)} className="size-4 accent-[var(--accent)]" />
                {LEVEL_LABELS[l]}
              </label>
            ))}
          </fieldset>
          <label className="flex items-center gap-2.5 text-sm text-ink-soft">
            <input type="checkbox" name="anywhere" value="1" defaultChecked={anywhere} className="size-4 accent-[var(--accent)]" />
            Include postings outside Canada
          </label>
          <button
            type="submit"
            className="btn btn-primary w-full"
          >
            {have ? "Update comparison" : "Compare my skills"}
          </button>
        </form>

        <section aria-labelledby="skills-heading" className="min-w-0 panel p-6">
          {gap ? (
            <div className="mb-5 space-y-2">
              <h2 id="skills-heading" className="text-xl font-semibold text-ink">
                You have {haveCount} of the top {topTen.length} skills
              </h2>
              {gap.missing_top_10.length > 0 && (
                <p className="text-sm text-ink-soft">
                  Biggest gaps: <span className="font-medium text-ink">{gap.missing_top_10.slice(0, 5).join(", ")}</span>.
                  {total !== undefined && <> Based on {pluralize(total, "open posting")}.</>}
                </p>
              )}
              {gap.unrecognized.length > 0 && (
                <p className="text-sm text-ink-faint">
                  Not recognized, so not counted: {gap.unrecognized.join(", ")}.
                </p>
              )}
            </div>
          ) : (
            <div className="mb-5 space-y-1">
              <h2 id="skills-heading" className="text-xl font-semibold text-ink">
                Most requested skills
              </h2>
              <p className="text-sm text-ink-soft">Enter your skills to see which of these you have.</p>
            </div>
          )}
          {skills.length ? (
            <SkillBars skills={skills} showHave={Boolean(gap)} />
          ) : (
            <p className="text-sm text-ink-soft">
              No open postings with readable descriptions match these settings yet. Try another level or role.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
