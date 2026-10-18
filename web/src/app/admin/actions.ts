"use server";

import { revalidatePath } from "next/cache";

import { api, attempt } from "@/lib/api";
import { visitorClient } from "@/lib/route";

const STATUSES = ["open", "in_progress", "resolved", "dismissed"] as const;

/** Update a problem report's status and note (the API checks the caller is an admin). */
export async function updateReport(form: FormData): Promise<void> {
  const id = Number(form.get("id"));
  const status = STATUSES.find((s) => s === form.get("status"));
  const note = String(form.get("admin_note") ?? "").slice(0, 2000).trim() || null;
  if (!Number.isSafeInteger(id) || !status) return;
  await attempt(api.admin.updateReport(await visitorClient(), id, { status, admin_note: note }));
  revalidatePath("/admin");
}
