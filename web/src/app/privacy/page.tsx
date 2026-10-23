import type { Metadata } from "next";
import Link from "next/link";

import { ProsePage, ProseSection } from "@/components/Prose";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "What Ghostless stores about you, why, how long it keeps it, and how to export or delete it.",
};

export default function PrivacyPage() {
  return (
    <ProsePage
      title="Privacy policy"
      updated="October 18, 2026"
      intro="Ghostless collects as little as it can, never sells or shares your data for advertising, and lets you export or delete everything at any time."
    >
      <ProseSection id="summary" title="The short version">
        <ul>
          <li>You can search jobs without an account. Browsing sets no tracking cookies.</li>
          <li>With an account, Ghostless stores your email, a hashed password, your settings, saved jobs and resumes.</li>
          <li>Your resume is used only to score it and match you with jobs. It is never shown to employers or anyone else.</li>
          <li>
            You can download or delete everything from your <Link href="/account" className="text-accent hover:underline">account page</Link>.
          </li>
        </ul>
      </ProseSection>

      <ProseSection id="what" title="What is stored">
        <ul>
          <li><strong>Account:</strong> your email address, an optional name, and your password stored as a one-way hash (it can&apos;t be read back, even by us).</li>
          <li>
            <strong>Google or GitHub sign-in:</strong> if you use one, Ghostless receives your name, your verified email address and
            the provider&apos;s id for your account. Nothing else: no contacts, repositories or files, and no access after you sign in.
          </li>
          <li><strong>Sessions:</strong> a sign-in token kept in a secure, httpOnly cookie, stored on our side only as a hash, plus the browser name so you can recognise your devices.</li>
          <li><strong>Settings:</strong> theme, text size and similar display choices, in a cookie and on your account.</li>
          <li><strong>Saved jobs:</strong> the jobs you save, each application&apos;s status, and any notes you write.</li>
          <li>
            <strong>Match feedback:</strong> jobs you mark &ldquo;Not interested&rdquo; on your matches, with the reason if you give
            one, so they stay hidden. Signed out, this stays in your browser.
          </li>
          <li>
            <strong>Resumes:</strong> when you upload a resume, the text is extracted and stored with the skills and details read
            from it. The file itself is not kept. Resumes you build are stored as you write them. If you check a resume without
            an account, it stays in your browser.
          </li>
          <li><strong>Problem reports:</strong> what you write, the page you were on, and your email if you give it.</li>
          <li>
            <strong>Usage counts:</strong> page views, counted without cookies and without storing IP addresses. A visitor is
            counted with a hash of the IP address and browser that changes every day, so nobody can be followed from one day to
            the next. Usage counts are deleted after about 13 months.
          </li>
        </ul>
      </ProseSection>

      <ProseSection id="why" title="Why it&apos;s used">
        <p>
          Only to run the features you use: keeping you signed in, syncing saved jobs, scoring your resume, sending account
          emails (confirming your address and resetting your password), fixing reported problems, and understanding which pages
          are useful. There is no advertising and no data sale.
        </p>
        <p>
          If you turn on &ldquo;Help improve job matching&rdquo; in Settings (it&apos;s off unless you do), your saved jobs,
          applications and &ldquo;not interested&rdquo; choices are also used, on our own servers, to measure and improve how jobs
          are matched. Your resume text isn&apos;t used for this and nothing is shared. Turning it off stops any further use; we
          keep a record of when you agreed and to which wording.
        </p>
      </ProseSection>

      <ProseSection id="ai" title="AI resume review">
        <p>
          Resume scores and suggestions are calculated by Ghostless itself, without AI. If the site offers an optional AI
          review and you ask for one, the text of your resume and of that job posting is sent to Anthropic, which provides the AI
          model, to write the review. Anthropic does not use API data to train its models by default. Nothing is sent unless you
          press the button.
        </p>
      </ProseSection>

      <ProseSection id="providers" title="Who helps run the site">
        <p>
          Ghostless uses a small number of service providers to host the website, the database and email delivery. They process
          data only to provide those services. Company logos are fetched by our server, so your browser never contacts a third
          party for them.
        </p>
      </ProseSection>

      <ProseSection id="retention" title="How long it&apos;s kept">
        <ul>
          <li>Account data: until you delete your account.</li>
          <li>Sign-in sessions: 30 days, or until you sign out.</li>
          <li>Password reset and confirmation links: they expire within a day and are cleared a week later.</li>
          <li>Usage counts: about 13 months.</li>
          <li>Problem reports: until they&apos;re resolved and no longer needed. Deleting your account removes your email from them.</li>
        </ul>
      </ProseSection>

      <ProseSection id="rights" title="Your choices">
        <ul>
          <li><strong>See and export:</strong> download everything stored about you as a file from your account page.</li>
          <li><strong>Correct:</strong> change your name, settings, saved jobs and resumes whenever you like.</li>
          <li><strong>Delete:</strong> delete your account, which permanently removes your sessions, saved jobs, notes and resumes.</li>
        </ul>
        <p>
          Ghostless is built in Ontario and follows Canada&apos;s federal privacy law (PIPEDA). Questions or requests go through the
          &ldquo;Report a problem&rdquo; link at the bottom of every page.
        </p>
      </ProseSection>

      <ProseSection id="changes" title="Changes">
        <p>If this policy changes in a way that matters, signed-in users will be told on the site before it takes effect.</p>
      </ProseSection>
    </ProsePage>
  );
}
