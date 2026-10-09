import { createNeonAuth } from "@neondatabase/auth/next/server";

let instance: ReturnType<typeof createNeonAuth> | undefined;

export function getAuth() {
  const baseUrl = process.env.NEON_AUTH_BASE_URL;
  const secret = process.env.NEON_AUTH_COOKIE_SECRET;
  if (!baseUrl || !secret || secret.length < 32) return null;
  const url = new URL(baseUrl);
  const localDevelopment = process.env.NODE_ENV === "development" && url.hostname === "127.0.0.1";
  if ((url.protocol !== "https:" && !localDevelopment) || url.username || url.password) {
    throw new Error("Invalid authentication configuration.");
  }
  instance ??= createNeonAuth({
    baseUrl,
    cookies: { secret, sessionDataTtl: 60, sameSite: "lax" },
    logLevel: "silent",
  });
  return instance;
}

export function sameOrigin(request: Request) {
  const expected = new URL(request.url);
  expected.host = request.headers.get("host") || expected.host;
  return request.headers.get("origin") === expected.origin;
}

export function apiError(detail: string, status: number) {
  return Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });
}
