import { cookies } from "next/headers";

const COOKIE_NAME = "ripken_session";
const MAX_AGE = 60 * 60 * 24 * 30; // 30 days

function getSecret(): Uint8Array<ArrayBuffer> {
  const secret = process.env.SESSION_SECRET;
  if (!secret) throw new Error("SESSION_SECRET env var is required");
  return new TextEncoder().encode(secret) as Uint8Array<ArrayBuffer>;
}

async function getKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    getSecret(),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function hexEncode(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function hexDecode(hex: string): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes as Uint8Array<ArrayBuffer>;
}

export async function createSessionCookie(): Promise<void> {
  const payload = JSON.stringify({ auth: true, iat: Date.now() });
  const key = await getKey();
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  );
  const token = `${Buffer.from(payload).toString("base64url")}.${hexEncode(sig)}`;

  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: MAX_AGE,
    path: "/",
  });
}

export async function verifySessionCookie(cookieValue: string): Promise<boolean> {
  try {
    const [payloadB64, sigHex] = cookieValue.split(".");
    if (!payloadB64 || !sigHex) return false;

    const payload = Buffer.from(payloadB64, "base64url");
    const key = await getKey();
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      hexDecode(sigHex),
      payload,
    );
    return valid;
  } catch {
    return false;
  }
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}

export const SESSION_COOKIE_NAME = COOKIE_NAME;
