import { apiError, getAuth, sameOrigin } from "@/lib/auth/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };
const allowed = {
  GET: new Set(["get-session", "token", "verify-email"]),
  POST: new Set([
    "sign-in/email",
    "sign-up/email",
    "sign-out",
    "send-verification-email",
    "request-password-reset",
    "reset-password",
  ]),
};

async function handle(request: Request, context: Context, method: "GET" | "POST") {
  const path = (await context.params).path.join("/");
  if (!allowed[method].has(path)) return apiError("Auth operation not available.", 404);
  if (method === "POST") {
    if (!sameOrigin(request)) return apiError("Origin not allowed.", 403);
    if ((await request.clone().arrayBuffer()).byteLength > 16384)
      return apiError("Request too large.", 413);
    if (path === "request-password-reset") {
      try {
        const body = await request.clone().json();
        const origin = request.headers.get("origin");
        if (body?.redirectTo !== `${origin}/auth/reset-password`)
          return apiError("Use the application's password reset page.", 400);
      } catch {
        return apiError("Invalid request body.", 400);
      }
    }
  }
  try {
    const auth = getAuth();
    if (!auth) return apiError("Sign-in is unavailable. Configure authentication first.", 503);
    const response = await auth.handler()[method](request, context);
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    return apiError("Authentication service is unavailable. Try again shortly.", 503);
  }
}

export const GET = (request: Request, context: Context) => handle(request, context, "GET");
export const POST = (request: Request, context: Context) => handle(request, context, "POST");
