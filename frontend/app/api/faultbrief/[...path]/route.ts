import { apiError, getAuth, sameOrigin } from "@/lib/auth/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function handle(request: Request, context: Context) {
  if (request.method === "POST" && !sameOrigin(request))
    return apiError("Origin not allowed.", 403);
  const { path } = await context.params;
  if (
    !path.every((segment) => /^[a-zA-Z0-9_-]+$/.test(segment)) ||
    !["me", "workspaces"].includes(path[0]) ||
    (path[0] === "me" && (path.length !== 1 || request.method !== "GET"))
  ) {
    return apiError("API operation not available.", 404);
  }
  try {
    const auth = getAuth();
    if (!auth) return apiError("Authentication is not configured.", 503);
    const session = await auth.getSession();
    if (session.error) return apiError("Authentication service is unavailable.", 503);
    if (!session.data?.user) return apiError("Authentication is required.", 401);
    const token = await auth.token();
    if (token.error || !token.data?.token) return apiError("Could not obtain an API token.", 503);
    const base = new URL(process.env.FAULTBRIEF_API_BASE_URL || "http://127.0.0.1:8000");
    const destination = new URL(`/v1/${path.join("/")}`, base);
    destination.search = new URL(request.url).search;
    const body = request.method === "POST" ? await request.arrayBuffer() : undefined;
    if (body && body.byteLength > 16384) return apiError("Request too large.", 413);
    const response = await fetch(destination, {
      method: request.method,
      headers: { Authorization: `Bearer ${token.data.token}`, "Content-Type": "application/json" },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.headers.get("content-type")?.includes("application/json"))
      return apiError("API returned an unexpected response.", 502);
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return apiError("Account service is unavailable. Try again shortly.", 503);
  }
}

export const GET = handle;
export const POST = handle;
