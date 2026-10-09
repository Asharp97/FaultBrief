"use client";

import { useEffect, useState, type FormEvent } from "react";

type Role = "owner" | "admin" | "support" | "viewer";
type Membership = { id: string; user_id: string; role: Role; active: boolean };
const roles: Role[] = ["viewer", "support", "admin", "owner"];

async function readResponse(response: Response) {
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Could not update workspace access.");
  return body;
}

export function WorkspaceMembers({
  workspace,
  userId,
}: {
  workspace: { id: string; name: string };
  userId: string;
}) {
  const [items, setItems] = useState<Membership[]>([]);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const mine = items.find((item) => item.user_id === userId);
  const canManage = mine?.active && mine.role === "owner";
  const endpoint = `/api/faultbrief/workspaces/${workspace.id}/memberships`;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const body = await readResponse(
          await fetch(`${endpoint}?limit=100`, { signal: controller.signal }),
        );
        setItems(body.items);
        setMore(body.items.length === 100);
      } catch (error) {
        if (!controller.signal.aborted)
          setMessage(error instanceof Error ? error.message : "Could not load memberships.");
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [endpoint]);

  async function loadMore() {
    setBusy(true);
    setMessage("");
    try {
      const body = await readResponse(await fetch(`${endpoint}?limit=100&offset=${items.length}`));
      setItems((current) => [...current, ...body.items]);
      setMore(body.items.length === 100 && items.length + body.items.length <= 10000);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load memberships.");
    } finally {
      setBusy(false);
    }
  }

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setMessage("");
    try {
      const item: Membership = await readResponse(
        await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: fields.get("user_id"), role: fields.get("role") }),
        }),
      );
      // Avoid disturbing the pagination offset when not all existing members are loaded.
      if (!more) setItems((current) => [...current, item]);
      form.reset();
      setMessage("Teammate added. Their account can now access this workspace.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add teammate.");
    } finally {
      setBusy(false);
    }
  }

  async function update(item: Membership, change: { role?: Role; active?: boolean }) {
    setBusy(true);
    setMessage("");
    try {
      const updated: Membership = await readResponse(
        await fetch(`${endpoint}/${item.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(change),
        }),
      );
      setItems((current) => current.map((member) => (member.id === updated.id ? updated : member)));
      setMessage(updated.active ? "Workspace access updated." : "Workspace access revoked.");
      if (updated.user_id === userId && !updated.active) window.location.reload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update access.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="account-card team-section" aria-label={`Team for ${workspace.name}`}>
      <p className="account-eyebrow">Workspace access</p>
      <h2>Team: {workspace.name}</h2>
      <p className="account-muted">
        Owners manage access. Admins configure integrations; support staff create investigations;
        viewers read results and leave feedback.
      </p>
      {message && (
        <p className="account-notice" role="status">
          {message}
        </p>
      )}
      <ul className="workspace-list">
        {items.map((item) => (
          <li key={item.id}>
            <strong>
              {item.user_id === userId ? "You" : "Teammate"} · {item.role} ·{" "}
              {item.active ? "active" : "inactive"}
            </strong>
            <code>{item.user_id}</code>
            {canManage && (
              <div className="member-actions">
                <form
                  className="member-role-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void update(item, {
                      role: new FormData(event.currentTarget).get("role") as Role,
                    });
                  }}
                >
                  <label className="account-muted">
                    Role for {item.user_id}
                    <select key={item.role} name="role" defaultValue={item.role} disabled={busy}>
                      {roles.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button className="button button-outline button-small" disabled={busy}>
                    Save role
                  </button>
                </form>
                <button
                  className="button button-outline button-small"
                  disabled={busy}
                  onClick={() => void update(item, { active: !item.active })}
                >
                  {item.active ? "Deactivate" : "Reactivate"}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {more && (
        <button
          className="button button-outline button-small"
          disabled={busy}
          onClick={() => void loadMore()}
        >
          Load more members
        </button>
      )}
      {canManage && (
        <form className="account-form" onSubmit={add}>
          <p className="account-muted">
            Ask your teammate to sign up, open their dashboard, and share their FaultBrief user ID.
            Add that ID here.
          </p>
          <label>
            Teammate user ID
            <input
              name="user_id"
              required
              pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          </label>
          <label>
            Starting role
            <select name="role" defaultValue="viewer">
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-teal" disabled={busy}>
            Add teammate
          </button>
        </form>
      )}
    </section>
  );
}
