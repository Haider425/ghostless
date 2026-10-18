import type { MetadataRoute } from "next";

const site = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // private or per-person pages, and endless search permutations
        disallow: ["/api/", "/admin", "/account", "/settings", "/saved", "/resume/matches", "/login", "/signup", "/reset-password", "/verify-email", "/forgot-password"],
      },
    ],
    sitemap: `${site}/sitemap.xml`,
  };
}
