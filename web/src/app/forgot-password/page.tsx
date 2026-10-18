import type { Metadata } from "next";

import { ForgotForm } from "./ForgotForm";

export const metadata: Metadata = { title: "Reset your password", robots: { index: false } };

export default function ForgotPasswordPage() {
  return <ForgotForm />;
}
