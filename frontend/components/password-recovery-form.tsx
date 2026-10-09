"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { authClient } from "@/lib/auth/client";

export function PasswordRecoveryForm({
  mode,
  configured,
}: {
  mode: "request" | "reset";
  configured: boolean;
}) {
  const resetting = mode === "reset";
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState("");
  const initialized = useRef(false);

  useEffect(() => {
    if (!resetting) {
      setReady(true);
      return;
    }
    if (initialized.current) return;
    initialized.current = true;
    const query = new URLSearchParams(window.location.search);
    const value = query.get("token") || "";
    if (!query.has("error") && value.length > 0 && value.length <= 2048) setToken(value);
    else setMessage("This reset link is missing, invalid, or expired. Request a new one.");
    // The bearer reset token stays in memory, outside browser storage and navigation history.
    window.history.replaceState(null, "", "/auth/reset-password");
    setReady(true);
  }, [resetting]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setMessage("");
    if (resetting && fields.get("password") !== fields.get("confirm")) {
      setMessage("The two passwords must match.");
      return;
    }
    setBusy(true);
    try {
      const result = resetting
        ? await authClient.resetPassword({ newPassword: String(fields.get("password")), token })
        : await authClient.requestPasswordReset({
            email: String(fields.get("email")).trim(),
            redirectTo: `${window.location.origin}/auth/reset-password`,
          });
      if (result.error) throw new Error();
      form.reset();
      setDone(true);
      setToken("");
      setMessage(
        resetting
          ? "Your password has been updated. Sign in with your new password."
          : "If an account exists for that email, you'll receive a password reset link. Check your inbox.",
      );
    } catch {
      setMessage(
        resetting
          ? "Could not reset the password. The link may be invalid or expired; request a new one."
          : "Password recovery is unavailable right now. Please try again shortly.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="account-page">
      <Link className="account-brand" href="/">
        FaultBrief<span>.</span>
      </Link>
      <section className="account-card auth-card">
        <p className="account-eyebrow">Account recovery</p>
        <h1>{resetting ? "Choose a new password." : "Get back to your workspace."}</h1>
        <p className="account-muted">
          {resetting
            ? "Use the recovery link from your email to update your password."
            : "Enter your account email. We'll send you a link to reset your password."}
        </p>
        {!configured && (
          <p className="account-notice" role="alert">
            Authentication is not configured yet.
          </p>
        )}
        {!done && ready && (!resetting || token) && (
          <form className="account-form" onSubmit={submit}>
            {resetting ? (
              <>
                <label>
                  New password
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    maxLength={128}
                  />
                </label>
                <label>
                  Confirm new password
                  <input
                    name="confirm"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    maxLength={128}
                  />
                </label>
              </>
            ) : (
              <label>
                Email address
                <input name="email" type="email" autoComplete="email" required maxLength={254} />
              </label>
            )}
            <button className="button button-ink" disabled={busy || !configured}>
              {busy ? "Please wait…" : resetting ? "Update password" : "Send reset link"}
            </button>
          </form>
        )}
        {message && (
          <p className="account-notice" role="status">
            {message}
          </p>
        )}
        {resetting && !done && (
          <p>
            <Link className="account-link" href="/auth/forgot-password">
              Request a new reset link
            </Link>
          </p>
        )}
        <Link className="account-link" href="/auth/sign-in">
          Back to sign in
        </Link>
      </section>
    </main>
  );
}
