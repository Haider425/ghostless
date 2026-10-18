import type { Metadata } from "next";

import { VerifyForm } from "./VerifyForm";

export const metadata: Metadata = { title: "Confirm your email", robots: { index: false } };

/**
 * Confirming takes a button press rather than happening on page load, because
 * some email scanners open links automatically and would use up the one-time link.
 */
export default async function VerifyEmailPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return <VerifyForm token={token ?? ""} />;
}
