import Link from "next/link";

import { CheckIcon, CrossIcon } from "./Icons";

/*
  Ranked skill demand as a table with inline bars. Every value is printed, so
  the bars are a reading aid rather than the only carrier of information.
  "You have it" is a solid bar, "missing" a hollow one, plus a text label:
  the distinction never relies on colour.
*/

export interface SkillBar {
  skill: string;
  postings: number;
  share: number;
  have?: boolean;
}

export function SkillBars({ skills, showHave = false }: { skills: SkillBar[]; showHave?: boolean }) {
  const max = Math.max(...skills.map((s) => s.share), 0.0001);
  return (
    <table className="w-full border-collapse text-sm">
      <caption className="sr-only">Skills ranked by share of matching postings</caption>
      <thead>
        <tr className="border-b border-line text-left text-ink-soft">
          <th scope="col" className="py-2 pr-3 font-medium">
            Skill
          </th>
          <th scope="col" className="w-full py-2 pr-3 font-medium">
            <span className="sr-only">Share of postings, as a bar</span>
          </th>
          <th scope="col" className="py-2 pr-3 text-right font-medium whitespace-nowrap">
            Share
          </th>
          <th scope="col" className="py-2 text-right font-medium whitespace-nowrap">
            Postings
          </th>
          {showHave && (
            <th scope="col" className="py-2 pl-4 text-left font-medium whitespace-nowrap">
              You
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {skills.map((item) => {
          const missing = showHave && !item.have;
          return (
            <tr key={item.skill} className="border-b border-line last:border-0">
              <th scope="row" className="py-2.5 pr-3 text-left font-medium whitespace-nowrap text-ink">
                <Link href={`/jobs?skill=${encodeURIComponent(item.skill)}`} className="hover:underline">
                  {item.skill}
                </Link>
              </th>
              <td className="py-2.5 pr-3" aria-hidden="true">
                <div className="h-2.5 min-w-10 sm:min-w-24">
                  <div
                    className={`h-full rounded-full ${
                      missing ? "border-[1.5px] border-bar-missing bg-transparent" : "bg-bar-have"
                    }`}
                    style={{ width: `${Math.max(2, (item.share / max) * 100)}%` }}
                  />
                </div>
              </td>
              <td className="py-2.5 pr-3 text-right whitespace-nowrap text-ink">{Math.round(item.share * 100)}%</td>
              <td className="py-2.5 text-right whitespace-nowrap text-ink-soft">
                {item.postings.toLocaleString("en-CA")}
              </td>
              {showHave && (
                <td className="py-2.5 pl-4 whitespace-nowrap">
                  {item.have ? (
                    <span className="inline-flex items-center gap-1.5 font-medium text-accent"><CheckIcon className="size-4" />You have it</span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-ink-soft"><CrossIcon className="size-4 text-ink-faint" />Missing</span>
                  )}
                </td>
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
