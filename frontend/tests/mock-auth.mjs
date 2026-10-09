// Loopback-only test provider and API double. Never used by application runtime.
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";

const sessions = new Map();
const workspaces = new Map();
const cookieName = "__Secure-neon-auth.session_token";
function json(res, data, status = 200, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(data));
}
createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:58110");
  if (url.pathname === "/health") return json(res, { status: "ok" });
  const cookie = (req.headers.cookie || "")
    .split(";")
    .map((c) => c.trim())
    .find((c) => c.startsWith(cookieName + "="))
    ?.slice(cookieName.length + 1);
  const session = sessions.get(cookie);
  if (url.pathname.startsWith("/neondb/auth/")) {
    const operation = url.pathname.slice("/neondb/auth/".length);
    if (operation === "get-session") return json(res, session || null);
    if (operation === "token")
      return json(
        res,
        session ? { token: "test-api-" + cookie } : { message: "Unauthorized" },
        session ? 200 : 401,
      );
    if (operation === "sign-out") {
      sessions.delete(cookie);
      return json(res, { success: true }, 200, {
        "Set-Cookie": `${cookieName}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`,
      });
    }
    if (["sign-in/email", "sign-up/email"].includes(operation)) {
      let text = "";
      for await (const part of req) text += part;
      const body = JSON.parse(text);
      if (body.password !== "synthetic-password-123")
        return json(
          res,
          { code: "INVALID_EMAIL_OR_PASSWORD", message: "Invalid email or password" },
          401,
        );
      const now = new Date().toISOString();
      const user = {
        id: randomUUID(),
        email: body.email,
        name: body.name || "Test engineer",
        emailVerified: true,
        createdAt: now,
        updatedAt: now,
      };
      if (body.email === "verify@example.invalid")
        return json(res, { user: { ...user, emailVerified: false }, token: null });
      const token = randomUUID();
      const record = {
        user,
        session: {
          id: randomUUID(),
          userId: user.id,
          token,
          createdAt: now,
          updatedAt: now,
          expiresAt: new Date(Date.now() + 3600000).toISOString(),
        },
      };
      sessions.set(token, record);
      return json(res, { user, token }, 200, {
        "Set-Cookie": `${cookieName}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600`,
      });
    }
    return json(res, { message: "Not found" }, 404);
  }
  const token = req.headers.authorization?.replace("Bearer test-api-", "");
  const actor = sessions.get(token);
  if (!actor) return json(res, { detail: "Unauthorized" }, 401);
  if (url.pathname === "/v1/me") return json(res, { id: actor.user.id });
  if (url.pathname === "/v1/workspaces") {
    const items = workspaces.get(actor.user.id) || [];
    if (req.method === "POST") {
      let text = "";
      for await (const part of req) text += part;
      const item = { id: randomUUID(), name: JSON.parse(text).name };
      workspaces.set(actor.user.id, [...items, item]);
      return json(res, item, 201);
    }
    return json(res, { items, limit: 100, offset: 0 });
  }
  json(res, { detail: "Not found" }, 404);
}).listen(58110, "127.0.0.1");
