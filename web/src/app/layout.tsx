import "@fontsource-variable/public-sans";
import "@fontsource-variable/familjen-grotesk";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { Analytics } from "@/components/Analytics";
import { SiteProvider } from "@/components/SiteContext";
import { ViewerChange } from "@/components/ViewerChange";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { api } from "@/lib/api";
import { htmlAttributes } from "@/lib/prefs";
import { currentPrefs, currentUser } from "@/lib/session";

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
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#15181e" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const [user, prefs, aiEnabled] = await Promise.all([currentUser(), currentPrefs(), api.aiEnabled()]);
  const viewer = user
    ? { id: user.id, name: user.name ?? null, email: user.email, role: user.role, emailVerified: user.email_verified }
    : null;
  return (
    <html lang="en-CA" {...htmlAttributes(prefs)} suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col antialiased">
        <SiteProvider value={{ viewer, prefs, aiEnabled }}>
          <SiteHeader />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
          <Analytics />
          <ViewerChange />
        </SiteProvider>
      </body>
    </html>
  );
}
