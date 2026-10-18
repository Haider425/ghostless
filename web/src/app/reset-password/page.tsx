import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/Form";

import { ResetForm } from "./ResetForm";

export const metadata: Metadata = { title: "Choose a new password", robots: { index: false } };

export default async function ResetPasswordPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  if (!token) {
    return (
      <AuthCard title="This link is incomplete" lead="Open the link from your email again, or ask for a new one.">
        <Link href="/forgot-password" className="link">Send a new reset link</Link>
      </AuthCard>
    );
  }
  return <ResetForm token={token} />;
}
