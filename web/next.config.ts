import type { NextConfig } from "next";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  images: {
    // company logos: website icons through Google's favicon service, resized and cached by Next
    remotePatterns: [{ protocol: "https", hostname: "www.google.com", pathname: "/s2/favicons" }],
    minimumCacheTTL: 60 * 60 * 24 * 7,
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default config;
