import type { Metadata } from "next";
import Link from "next/link";

import { ProsePage, ProseSection } from "@/components/Prose";

export const metadata: Metadata = {
  title: "Terms of use",
  description: "The terms for using Ghostless.",
};

export default function TermsPage() {
  return (
    <ProsePage
      title="Terms of use"
      updated="October 17, 2026"
      intro="Plain terms for a free service. By using Ghostless you agree to them."
    >
      <ProseSection id="service" title="What Ghostless is">
        <p>
          Ghostless collects public job postings from employers&apos; own career sites and shows them with extra context: how long
          each has been open, whether it was reposted, and what it discloses. You always apply on the employer&apos;s site. Ghostless
          is not an employer, a recruiter or an agent for any employer.
        </p>
      </ProseSection>

      <ProseSection id="accuracy" title="Signals are evidence, not verdicts">
        <p>
          Ghost signals, match scores and resume suggestions come from automated rules. They can be wrong, and a flagged posting
          may be a genuine opening. Check the original posting before deciding, and{" "}
          <Link href="/how-it-works" className="text-accent hover:underline">read how the signals work</Link>. Nothing on the
          site is a promise of an interview or a job.
        </p>
      </ProseSection>

      <ProseSection id="account" title="Your account">
        <ul>
          <li>Keep your password private. You&apos;re responsible for what happens under your account.</li>
          <li>One person per account. Accounts are free.</li>
          <li>You can delete your account at any time from the account page.</li>
        </ul>
      </ProseSection>

      <ProseSection id="content" title="Your content">
        <p>
          Resumes, notes and reports you add stay yours. You let Ghostless store and process them only to provide the features you
          use, as described in the <Link href="/privacy" className="text-accent hover:underline">privacy policy</Link>. Don&apos;t
          upload anything you don&apos;t have the right to share.
        </p>
      </ProseSection>

      <ProseSection id="use" title="Fair use">
        <ul>
          <li>Don&apos;t scrape the site in bulk, overload it, or try to get around rate limits or access other people&apos;s data.</li>
          <li>Don&apos;t use Ghostless to harass employers or other users, or to send spam through problem reports.</li>
          <li>Accounts that break these rules may be suspended.</li>
        </ul>
      </ProseSection>

      <ProseSection id="liability" title="No warranty">
        <p>
          Ghostless is provided as it is, without warranties. Postings belong to their employers and may change or close at any time.
          To the extent the law allows, Ghostless isn&apos;t liable for decisions made using the site or for losses from it being
          unavailable.
        </p>
      </ProseSection>

      <ProseSection id="changes" title="Changes">
        <p>
          These terms may change as the product grows. Signed-in users will be told about significant changes on the site. These
          terms are governed by the laws of Ontario, Canada.
        </p>
      </ProseSection>
    </ProsePage>
  );
}
