// Loopback-only provider/API double. Synthetic accounts and mailbox; never application runtime.
import { createServer } from "node:http";
import { randomUUID, generateKeyPairSync, sign } from "node:crypto";

const sessions = new Map();
const apiTokens = new Map();
const { privateKey } = generateKeyPairSync("ed25519");
function apiToken(cookie, user) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const now = Math.floor(Date.now() / 1000);
  const data =
    encode({ alg: "EdDSA", kid: "synthetic-provider-key" }) +
    "." +
    encode({
      iss: "http://127.0.0.1:58110",
      sub: user.id,
      iat: now,
      exp: now + 3600,
    });
  const token = data + "." + sign(null, Buffer.from(data), privateKey).toString("base64url");
  apiTokens.set(token, cookie);
  return token;
}
const accounts = new Map();
const resets = new Map();
const mailbox = new Map();
const workspaces = new Map();
const memberships = new Map();
const cookieName = "__Secure-neon-auth.session_token";
function json(res, data, status = 200, headers = {}) {
  res.writeHead(status, { "Content-Type": "application/json", ...headers });
  res.end(JSON.stringify(data));
}
async function body(req) {
  let text = "";
  for await (const part of req) text += part;
  return text ? JSON.parse(text) : {};
}
function account(email, name = "Test engineer") {
  if (!accounts.has(email)) {
    const now = new Date().toISOString();
    accounts.set(email, {
      password: "synthetic-password-123",
      user: {
        id: randomUUID(),
        email,
        name,
        emailVerified: email !== "verify@example.invalid",
        createdAt: now,
        updatedAt: now,
      },
    });
  }
  return accounts.get(email);
}
resets.set("expired-synthetic-reset-token", { email: "expired@example.invalid", expires: 0 });
createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:58110");
  if (url.pathname === "/health") return json(res, { status: "ok" });
  if (url.pathname === "/test/mailbox")
    return json(res, mailbox.get(url.searchParams.get("email")) || null);
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
        session ? { token: apiToken(cookie, session.user) } : { message: "Unauthorized" },
        session ? 200 : 401,
      );
    if (operation === "sign-out") {
      sessions.delete(cookie);
      return json(res, { success: true }, 200, {
        "Set-Cookie": `${cookieName}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`,
      });
    }
    if (operation === "request-password-reset") {
      const data = await body(req);
      if (accounts.has(data.email)) {
        const token = randomUUID();
        resets.set(token, { email: data.email, expires: Date.now() + 300000 });
        mailbox.set(data.email, { url: `${data.redirectTo}?token=${token}` });
      }
      return json(res, {
        status: true,
        message: "If this email exists, check your email for a reset link",
      });
    }
    if (operation === "reset-password") {
      const data = await body(req);
      const record = resets.get(data.token);
      if (!record || record.expires < Date.now())
        return json(res, { code: "INVALID_TOKEN", message: "Invalid token" }, 400);
      if (data.newPassword.length < 8 || data.newPassword.length > 128)
        return json(res, { code: "PASSWORD_TOO_SHORT", message: "Invalid password" }, 400);
      accounts.get(record.email).password = data.newPassword;
      resets.delete(data.token);
      return json(res, { status: true });
    }
    if (["sign-in/email", "sign-up/email"].includes(operation)) {
      const data = await body(req);
      const record = account(data.email, data.name);
      if (data.password !== record.password)
        return json(
          res,
          { code: "INVALID_EMAIL_OR_PASSWORD", message: "Invalid email or password" },
          401,
        );
      const user = record.user;
      if (!user.emailVerified) return json(res, { user, token: null });
      const now = new Date().toISOString();
      const token = randomUUID();
      sessions.set(token, {
        user,
        session: {
          id: randomUUID(),
          userId: user.id,
          token,
          createdAt: now,
          updatedAt: now,
          expiresAt: new Date(Date.now() + 3600000).toISOString(),
        },
      });
      return json(res, { user, token }, 200, {
        "Set-Cookie": `${cookieName}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600`,
      });
    }
    return json(res, { message: "Not found" }, 404);
  }
  const token = req.headers.authorization?.replace("Bearer ", "");
  const actor = sessions.get(apiTokens.get(token));
  if (!actor) return json(res, { detail: "Unauthorized" }, 401);
  if (url.pathname === "/v1/me") return json(res, { id: actor.user.id });
  if (url.pathname === "/v1/workspaces") {
    if (req.method === "POST") {
      const item = { id: randomUUID(), name: (await body(req)).name };
      workspaces.set(item.id, item);
      const member = {
        id: randomUUID(),
        workspace_id: item.id,
        user_id: actor.user.id,
        role: "owner",
        active: true,
      };
      memberships.set(member.id, member);
      return json(res, item, 201);
    }
    const ids = new Set(
      [...memberships.values()]
        .filter((m) => m.user_id === actor.user.id && m.active)
        .map((m) => m.workspace_id),
    );
    return json(res, {
      items: [...workspaces.values()].filter((w) => ids.has(w.id)),
      limit: 100,
      offset: 0,
    });
  }
  const match = url.pathname.match(/^\/v1\/workspaces\/([^/]+)\/memberships(?:\/([^/]+))?$/);
  if (match) {
    const [, wid, mid] = match;
    const mine = [...memberships.values()].find(
      (m) => m.workspace_id === wid && m.user_id === actor.user.id && m.active,
    );
    if (!mine) return json(res, { detail: "Workspace not found." }, 404);
    if (req.method === "GET")
      return json(res, {
        items: [...memberships.values()].filter((m) => m.workspace_id === wid),
        limit: 100,
        offset: 0,
      });
    if (mine.role !== "owner")
      return json(res, { detail: "Only workspace owners can manage memberships." }, 403);
    const data = await body(req);
    if (req.method === "POST") {
      if (![...accounts.values()].some((a) => a.user.id === data.user_id))
        return json(res, { detail: "Account not found. Ask the teammate to sign in first." }, 404);
      if (
        [...memberships.values()].some((m) => m.workspace_id === wid && m.user_id === data.user_id)
      )
        return json(res, { detail: "Resource or relationship conflict." }, 409);
      const member = {
        id: randomUUID(),
        workspace_id: wid,
        user_id: data.user_id,
        role: data.role || "viewer",
        active: true,
      };
      memberships.set(member.id, member);
      return json(res, member, 201);
    }
    const member = memberships.get(mid);
    if (!member || member.workspace_id !== wid)
      return json(res, { detail: "Membership not found." }, 404);
    const changed = { ...member, ...data };
    const otherOwner = [...memberships.values()].some(
      (m) => m.workspace_id === wid && m.id !== mid && m.role === "owner" && m.active,
    );
    if (
      member.active &&
      member.role === "owner" &&
      (!changed.active || changed.role !== "owner") &&
      !otherOwner
    )
      return json(res, { detail: "A workspace must keep at least one active owner." }, 409);
    memberships.set(mid, changed);
    return json(res, changed);
  }
  json(res, { detail: "Not found" }, 404);
}).listen(58110, "127.0.0.1");
