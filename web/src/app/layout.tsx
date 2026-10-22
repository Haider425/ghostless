import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Caveat, Figtree } from "next/font/google";
import localFont from "next/font/local";
import { type ReactNode, Suspense } from "react";

import { Analytics } from "@/components/Analytics";
import { ApplyPrompt } from "@/components/ApplyPrompt";
import { NavProgress } from "@/components/NavProgress";
import { SiteProvider } from "@/components/SiteContext";
import { ViewerChange } from "@/components/ViewerChange";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { api } from "@/lib/api";
import { htmlAttributes } from "@/lib/prefs";
import { currentPrefs, currentUser } from "@/lib/session";

/*
  Inter, self-hosted (Latin). next/font preloads it, so text doesn't reflow
  when it arrives.
*/
const inter = localFont({
  src: "../../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  weight: "100 900",
  variable: "--font-inter",
  display: "swap",
  adjustFontFallback: "Arial",
});

/*
  The brand faces (self-hosted at build time, no requests to Google):
  Bricolage Grotesque for headlines and the wordmark, Figtree for the home
  page's text, Caveat for the handwritten notes.
*/
const brand = Bricolage_Grotesque({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-bricolage", display: "swap" });
const friendly = Figtree({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-figtree", display: "swap" });
const hand = Caveat({ subsets: ["latin"], weight: ["700"], variable: "--font-caveat", display: "swap" });

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "Ghostless: tech jobs that are actually hiring", template: "%s | Ghostless" },
  description:
    "Search tech internships and jobs in Canada with their true posting age, repost history and ghost job signals, and see how your resume matches each one.",
  applicationName: "Ghostless",
  openGraph: {
    type: "website",
    siteName: "Ghostless",
    title: "Ghostless: tech jobs that are actually hiring",
    description: "Every posting's true age, repost history and ghost job signals, plus resume matching. Free.",
    locale: "en_CA",
  },
  twitter: { card: "summary" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbf7f0" },
    { media: "(prefers-color-scheme: dark)", color: "#191713" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const [user, prefs, aiEnabled] = await Promise.all([currentUser(), currentPrefs(), api.aiEnabled()]);
  const viewer = user
    ? { id: user.id, name: user.name ?? null, email: user.email, role: user.role, emailVerified: user.email_verified }
    : null;
  return (
    <html lang="en-CA" {...htmlAttributes(prefs)} className={`${inter.variable} ${brand.variable} ${friendly.variable} ${hand.variable}`} suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col antialiased">
        <SiteProvider value={{ viewer, prefs, aiEnabled }}>
          <Suspense>
            <NavProgress />
          </Suspense>
          <SiteHeader />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
          <ApplyPrompt />
          <Analytics />
          <ViewerChange />
        </SiteProvider>
      </body>
    </html>
  );
}
