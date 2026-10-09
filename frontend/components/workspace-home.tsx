"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { authClient } from "@/lib/auth/client";
import { WorkspaceMembers } from "@/components/workspace-members";

type Workspace = { id: string; name: string };
export function WorkspaceHome({ name, email }: { name: string; email: string }) {
  const [items, setItems] = useState<Workspace[]>([]);
  const [identity, setIdentity] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Workspace | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [user, workspaces] = await Promise.all([
          fetch("/api/faultbrief/me", { signal: controller.signal }),
          fetch("/api/faultbrief/workspaces?limit=100", { signal: controller.signal }),
        ]);
        if (user.status === 401 || workspaces.status === 401) {
          window.location.assign("/auth/sign-in");
          return;
        }
        if (!user.ok || !workspaces.ok)
          throw new Error(
            "Could not connect your account to FaultBrief. Check that the API is running and configured.",
          );
        setIdentity((await user.json()).id);
        setItems((await workspaces.json()).items);
      } catch (error) {
        if (!controller.signal.aborted)
          setMessage(error instanceof Error ? error.message : "Could not load workspaces.");
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch("/api/faultbrief/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: new FormData(form).get("name") }),
      });
      if (!response.ok) throw new Error("Could not create the workspace. Please try again.");
      const workspace: Workspace = await response.json();
      setItems((current) => [...current, workspace]);
      form.reset();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Workspace creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      const result = await authClient.signOut();
      if (result.error) throw new Error();
      window.location.assign("/auth/sign-in");
    } catch {
      setBusy(false);
      setMessage("Sign-out failed. Please try again.");
    }
  }

  async function copyToken() {
    try {
      const result = await authClient.token();
      if (result.error || !result.data?.token) throw new Error();
      await navigator.clipboard.writeText(result.data.token);
      setMessage("API token copied. Keep it private and refresh it when it expires.");
    } catch {
      setMessage("Could not copy a token. Use the authenticated /api/auth/token request in Bruno.");
    }
  }

  return (
    <main className="account-page workspace-page">
      <header className="account-header">
        <Link className="account-brand" href="/">
          FaultBrief<span>.</span>
        </Link>
        <button className="button button-outline button-small" onClick={signOut} disabled={busy}>
          Sign out
        </button>
      </header>
      <p className="account-eyebrow">Private workspace</p>
      <h1>Hello, {name || "there"}.</h1>
      <p className="account-muted">{email}</p>
      {message && (
        <p className="account-notice" role="status">
          {message}
        </p>
      )}
      <div className="account-grid">
        <section className="account-card">
          <h2>Your companies</h2>
          <p className="account-muted">
            Each workspace belongs to a company. Its affected SaaS customers are separate records.
          </p>
          {items.length ? (
            <ul className="workspace-list">
              {items.map((item) => (
                <li key={item.id}>
                  <strong>{item.name}</strong>
                  <code>{item.id}</code>
                  <button
                    className="button button-outline button-small"
                    onClick={() => setSelected(item)}
                  >
                    View team for {item.name}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>No workspaces yet. Create your first one below.</p>
          )}
          <form className="account-form" onSubmit={create}>
            <label>
              Company or workspace name
              <input name="name" required maxLength={120} placeholder="Acme SaaS" />
            </label>
            <button className="button button-teal" disabled={busy || !identity}>
              Create workspace
            </button>
          </form>
        </section>
        <section className="account-card">
          <h2>Account connection</h2>
          <p>
            {identity
              ? "Your verified identity is connected to the FaultBrief API."
              : "Connecting your account…"}
          </p>
          {identity && (
            <>
              <p className="account-muted">Your FaultBrief user ID</p>
              <code className="account-id">{identity}</code>
              <p>
                <button
                  className="button button-outline button-small"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(identity);
                      setMessage("User ID copied. Share it with your workspace owner.");
                    } catch {
                      setMessage("Could not copy. Select and copy your user ID above.");
                    }
                  }}
                >
                  Copy my user ID
                </button>
              </p>
            </>
          )}
          <p className="account-muted">
            Workspace membership controls what you can access. Your passwords and sessions stay with
            Neon Auth.
          </p>
          <button className="button button-outline" onClick={copyToken}>
            Copy API token for Bruno
          </button>
          <p className="account-fine">
            For your own API testing. The token is copied only when you press this button; it is
            never saved to browser storage.
          </p>
        </section>
      </div>
      {selected && identity && (
        <WorkspaceMembers key={selected.id} workspace={selected} userId={identity} />
      )}
    </main>
  );
}
