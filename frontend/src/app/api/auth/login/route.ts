import { NextRequest, NextResponse } from "next/server";
import { createSessionCookie } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const password = body.password;

  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    return NextResponse.json(
      { error: "DASHBOARD_PASSWORD not configured" },
      { status: 500 },
    );
  }

  if (password !== expected) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  await createSessionCookie();
  return NextResponse.json({ ok: true });
}
