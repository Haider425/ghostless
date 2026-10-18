import { NextResponse } from "next/server";

import { api } from "@/lib/api";
import { signedIn, visitorClient } from "@/lib/route";

/** "Download my data": everything stored about the account, as a JSON file. */
export async function GET() {
  if (!(await signedIn())) return NextResponse.redirect(new URL("/login?next=/account", process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"));
  const data = await api.exportData(await visitorClient());
  return new NextResponse(JSON.stringify(data, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Disposition": `attachment; filename="ghostless-data-${new Date().toISOString().slice(0, 10)}.json"`,
      "Cache-Control": "private, no-store",
    },
  });
}
