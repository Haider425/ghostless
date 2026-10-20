import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { FLAG_TEXT } from "@/lib/format";

export const metadata: Metadata = {
  title: "How it works",
  description: "How Ghostless collects postings and calculates ghost job signals, true posting ages and disclosures.",
};

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-8 space-y-3">
      <h2 id={`${id}-title`} className="text-2xl font-semibold text-ink">
        {title}
      </h2>
      <div className="space-y-3 text-ink-soft">{children}</div>
    </section>
  );
}

const FLAG_DETAIL: Record<string, string> = {
  not_existing_vacancy:
    "Since January 1, 2026, Ontario requires employers with 25 or more staff to say whether a public posting is for an existing vacancy. Ghostless flags a posting only when it says this about itself, such as \u201cThis posting is not for an existing vacancy\u201d or \u201cThis is an evergreen requisition\u201d, and quotes that sentence on the job's page so you can check it. A job duty like building pipelines for future hiring needs doesn't count. This flag alone makes a posting high risk, because the employer is telling you it isn't a specific opening.",
  reposted:
    "Ghostless fingerprints every posting by its title, location and description, with requisition numbers and dates removed. When a posting disappears and the same role reappears under a new listing, the new one is linked to the old one. Large employers post many different roles with the same title, so the description has to match too.",
  duplicate_posting:
    "Two or more live listings at the same company have the same title, the same locations and the same description at the same time. The same role posted for different cities isn't a duplicate, and listings without a description are never compared, because title and city alone can't tell different teams apart.",
  open_unusually_long:
    "A posting is flagged when it has been open more than 60 days and more than twice as long as that employer usually takes for that kind of role. The usual time is the median for postings Ghostless has watched open and close, and needs at least five of them.",
};

export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 pt-10 pb-20 sm:px-6">
      <header className="mb-10 space-y-3">
        <h1 className="page-title">How Ghostless works</h1>
        <p className="page-lead">
          Job sites show a posting date that resets every time a role is reposted. Ghostless keeps its own record of
          every posting instead, and the signals come from that record.
        </p>
      </header>

      <div className="space-y-12">
        <Section id="collection" title="Where the postings come from">
          <p>
            Every day, Ghostless reads the public career sites of{" "}
            <Link href="/companies" className="text-accent hover:underline">
              the employers it tracks
            </Link>
            , the same pages you would visit yourself. It follows each site&apos;s robots.txt rules, identifies itself,
            and slows down when a site asks it to. Sites that prohibit automated collection are left out, which is why
            Meta isn&apos;t included.
          </p>
          <p>
            The list of employers grows by itself. Each day Ghostless also reads public internship and new grad lists that
            students keep on GitHub, such as{" "}
            <a href="https://github.com/SimplifyJobs/Summer2027-Internships" className="text-accent hover:underline">
              SimplifyJobs
            </a>
            . When a posting there links to a Greenhouse, Lever, Ashby or Workday job board Ghostless doesn&apos;t read
            yet, that board is added and read from then on, a batch each day, so every company is revisited every few
            days. Large Workday employers are searched for internships, co-ops and new grad roles. Until a company&apos;s
            own board is read, its postings appear as the list shows them: title, places and season, with a link to apply.
          </p>
          <p>
            LinkedIn isn&apos;t read: its terms and robots.txt forbid automated collection. Most LinkedIn postings for tech
            roles are copies of a posting on the employer&apos;s own career site, which is where Ghostless reads them.
          </p>
          <p>Every job links to the employer&apos;s original posting. You always apply on their site.</p>
        </Section>

        <Section id="matching" title="Resume match scores">
          <p>
            A match score reads the whole posting and your whole resume, not just a skills section. The posting is split
            into what it requires, what&apos;s nice to have, the duties and the boilerplate (benefits, company blurb), which is
            ignored. From that come its skills, the years of experience and degree it asks for, whether you must be in
            school, and the terms it keeps using for the work itself.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Required skills, 35 points. A skill shown in a job or project counts fully; one only named in a skills list counts less.</li>
            <li>Nice-to-haves, 10 points.</li>
            <li>The posting&apos;s key terms that your resume uses too, 15 points.</li>
            <li>Experience, 20 points: your career stage and years against what it asks for.</li>
            <li>Education, 10 points: degree, field, and being enrolled when it&apos;s required.</li>
            <li>Role and title, 10 points: how much of your resume is this kind of work.</li>
          </ul>
          <p>
            A role meant for a different career stage, like a senior role for a student, is capped however well the skills
            match. Every requirement is listed on the job&apos;s page as met, partly met or missing, with what to change.
            It&apos;s rule based, free and runs on Ghostless&apos;s own server; your resume isn&apos;t sent anywhere else.
          </p>
        </Section>

        <Section id="age" title="True posting age">
          <p>
            The first time Ghostless sees a posting, it records the date. That date never changes, even when the
            employer&apos;s site shows a fresher one. Postings that were already up when Ghostless began watching an
            employer are shown as &ldquo;open at least&rdquo; that many days, because their real start is earlier.
          </p>
        </Section>

        <Section id="signals" title="Ghost signals">
          <p>
            A ghost job is a posting that isn&apos;t backed by a real plan to hire soon. No outside data can prove that,
            so Ghostless looks for evidence instead. Each posting gets one of three levels:
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <span className="font-medium text-ink">No flags:</span> none of the signals below.
            </li>
            <li>
              <span className="font-medium text-ink">Some flags:</span> one signal.
            </li>
            <li>
              <span className="font-medium text-ink">High ghost risk:</span> two or more signals, or the employer says
              it isn&apos;t a real vacancy.
            </li>
          </ul>
          <dl className="space-y-5 pt-2">
            {Object.entries(FLAG_TEXT).map(([key, flag]) => (
              <div key={key} className="border-l-[3px] border-line-strong pl-4">
                <dt className="font-semibold text-ink">{flag.short}</dt>
                <dd className="mt-1">{FLAG_DETAIL[key]}</dd>
              </div>
            ))}
          </dl>
          <p>
            Signals are evidence, not verdicts. A long-open role can be genuinely hard to fill, and a reposted role
            may have reopened after a hire fell through.
          </p>
        </Section>

        <Section id="disclosures" title="Pay and vacancy disclosures">
          <p>
            Ontario&apos;s job posting rules also require a pay range of at most $50,000 and a statement about whether AI
            is used to screen applicants. Ghostless reads these from the posting text and quotes the sentence it read them
            from. When the text doesn&apos;t say, the page says so rather than guessing. Some employers, Stripe among
            them, add pay only on their own careers site rather than in the posting data Ghostless receives, so check the
            original posting before ruling a job out.
          </p>
        </Section>

        <Section id="limits" title="Known limits">
          <ul className="list-disc space-y-1 pl-5">
            <li>Google only allows the first page of each search to be read, so its coverage is partial.</li>
            <li>Apple and Shopify don&apos;t publish full descriptions in their listings, so their skills are incomplete.</li>
            <li>
              Banks and other large employers on Workday need one request per posting for its description, so new
              postings&apos; descriptions arrive in batches over a few daily runs.
            </li>
            <li>Levels, roles and skills are detected with rules. Unusual titles can be misread.</li>
            <li>Postings known only from a job list have no description, so their match scores use the title, level and role.</li>
          </ul>
          <p>
            Spotted a mistake?{" "}
            <a href="https://github.com/Haider425/ghostless/issues/new/choose" className="text-accent hover:underline">
              Report it on GitHub
            </a>
            .
          </p>
        </Section>
      </div>
    </div>
  );
}
