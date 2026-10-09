"use client";

import Link from "next/link";
import { isAuthApiError } from "@neondatabase/auth/next";
import { useState, type FormEvent } from "react";
import { authClient } from "@/lib/auth/client";

export function AuthForm({
  mode,
  configured,
}: {
  mode: "sign-in" | "sign-up";
  configured: boolean;
}) {
  const signup = mode === "sign-up";
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setMessage("");
    try {
      const credentials = {
        email: String(fields.get("email")).trim(),
        password: String(fields.get("password")),
      };
      const result = signup
        ? await authClient.signUp.email({
            ...credentials,
            name: String(fields.get("name")).trim(),
            callbackURL: `${window.location.origin}/auth/sign-in`,
          })
        : await authClient.signIn.email(credentials);
      if (result.error) {
        setMessage(
          signup
            ? "Could not create the account. Check your details or sign in if you already have an account."
            : "Sign-in failed. Check your email and password, or verify your email first.",
        );
        return;
      }
      form.reset();
      const session = await authClient.getSession();
      if (!session.data?.user) {
        setMessage("Check your email to verify your account, then sign in.");
        return;
      }
      // A full navigation avoids showing an old cached unauthenticated server page.
      window.location.assign("/dashboard");
    } catch (error) {
      setMessage(
        isAuthApiError(error) && [400, 401, 403, 422].includes(error.status)
          ? signup
            ? "Could not create the account. Check your details or sign in if you already have an account."
            : "Sign-in failed. Check your email and password, or verify your email first."
          : "Sign-in is temporarily unavailable. Please try again.",
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
      <div className="account-card auth-card">
        <p className="account-eyebrow">Your support workspace</p>
        <h1>{signup ? "Follow the evidence." : "Welcome back."}</h1>
        <p className="account-muted">
          {signup
            ? "Create your account. You’ll set up your company workspace next."
            : "Sign in to your company’s FaultBrief workspace."}
        </p>
        {!configured && (
          <p className="account-notice" role="alert">
            Sign-in is not configured yet. Follow the local setup guide to enable it.
          </p>
        )}
        <form onSubmit={submit} className="account-form">
          {signup && (
            <label>
              Full name
              <input name="name" autoComplete="name" required maxLength={120} />
            </label>
          )}
          <label>
            Email address
            <input name="email" type="email" autoComplete="email" required maxLength={254} />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={signup ? "new-password" : "current-password"}
              required
              minLength={signup ? 8 : 1}
              maxLength={128}
            />
          </label>
          <button className="button button-ink" type="submit" disabled={busy || !configured}>
            {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
          </button>
        </form>
        {message && (
          <p className="account-notice" role="status">
            {message}
          </p>
        )}
        <p className="account-muted">
          {signup ? "Already have an account?" : "New to FaultBrief?"}{" "}
          <Link className="account-link" href={signup ? "/auth/sign-in" : "/auth/sign-up"}>
            {signup ? "Sign in" : "Create an account"}
          </Link>
        </p>
        <p className="account-fine">
          Your credentials are managed by Neon Auth. FaultBrief uses your verified identity to check
          workspace access.
        </p>
      </div>
    </main>
  );
}
