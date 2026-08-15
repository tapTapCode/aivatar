"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { AuthProviderMark } from "@/components/AuthProviderMark";
import { authApi, ApiError } from "@/lib/api";
import type { AuthConfig, Session } from "@/lib/types";

type View = "login" | "register" | "forgot" | "reset" | "verify";
type Method = "email" | "sso";
type Result = { title: string; copy: string; label: string; href: string };

const copy: Record<View, [string, string]> = {
  login: ["Welcome back", "Sign in to continue to your private production workspace."],
  register: ["Create your account", "Start building consistent video stories with your team."],
  forgot: ["Reset your password", "Enter your email and we’ll send a secure reset link."],
  reset: ["Choose a new password", "Your new password must contain at least 12 characters."],
  verify: ["Verifying your email", "Please wait while we activate your workspace."],
};

function safeNext(value: string | null) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/";
}

const oauthErrors: Record<string, string> = {
  oauth_state: "Social sign-in expired. Start again from this page.",
  oauth_failed: "Google or Apple could not verify this account.",
  oauth_cancelled: "Social sign-in was cancelled.",
  oauth_paused: "That sign-in method is paused. Use Google or email for now.",
};

function disabledProviderNotice(name: string) {
  if (name === "Apple") {
    return "Apple sign-in is paused. Use Google or email for now.";
  }
  return `${name} SSO needs OAuth credentials before it can be used.`;
}

export function AuthScreen({
  onAuthenticated,
}: {
  onAuthenticated: (session: Session) => void;
}) {
  const [view, setView] = useState<View>("login");
  const [method, setMethod] = useState<Method>("email");
  const [token, setToken] = useState("");
  const [nextPath, setNextPath] = useState("/");
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get("view");
    const requestedView: View =
      requested && requested in copy ? (requested as View) : "login";
    queueMicrotask(() => {
      setView(requestedView);
      setMethod(params.get("method") === "sso" ? "sso" : "email");
      setToken(params.get("token") ?? "");
      setNextPath(safeNext(params.get("next")));
      const oauthError = params.get("error");
      if (oauthError) {
        setNotice(
          oauthErrors[oauthError] ??
            "Social sign-in could not be completed. Please try again.",
        );
      }
    });
  }, []);

  useEffect(() => {
    authApi
      .config()
      .then(setConfig)
      .catch(() => setNotice("Unable to load sign-in providers."));
  }, []);

  useEffect(() => {
    if (view !== "verify") return;
    if (!token) {
      queueMicrotask(() => {
        setResult({
          title: "Invalid verification link",
          copy: "This verification link is incomplete.",
          label: "Return to sign in",
          href: "/",
        });
      });
      return;
    }
    queueMicrotask(() => setBusy(true));
    authApi
      .verifyEmail(token)
      .then(() =>
        setResult({
          title: "Email verified",
          copy: "Your workspace is ready.",
          label: "Open workspace",
          href: nextPath,
        }),
      )
      .catch((error: Error) =>
        setResult({
          title: "Unable to verify email",
          copy: error.message,
          label: "Return to sign in",
          href: "/",
        }),
      )
      .finally(() => setBusy(false));
  }, [nextPath, token, view]);

  const providers = useMemo(
    () =>
      config?.providers ?? [
        { name: "Google" as const, enabled: false },
        { name: "Apple" as const, enabled: false },
      ],
    [config],
  );

  function switchView(next: View) {
    setView(next);
    setMethod("email");
    setNotice("");
    setResult(null);
  }

  async function submit(
    event: FormEvent<HTMLFormElement>,
    action: (data: FormData) => Promise<void>,
  ) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await action(new FormData(event.currentTarget));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const [title, intro] = copy[view];
  const supportsMethods = view === "login" || view === "register";

  return (
    <main className="auth-layout">
      <section className="auth-story" aria-label="Aivatar">
        <Link className="auth-brand" href="/" aria-label="Aivatar sign in">
          <Image src="/logo-aivatar.png" alt="Aivatar" width={1000} height={667} priority />
        </Link>
        <div className="story-copy">
          <p className="eyebrow">AI video workspace</p>
          <h1>Move from an idea to a finished story.</h1>
          <p>
            Create presenter videos, visual narratives, and repeatable formats from one
            private production workspace.
          </p>
        </div>
        <div className="story-card" aria-hidden="true">
          <span className="story-orb" />
          <div>
            <strong>Your next video</strong>
            <small>Script · Presenter · Visuals · Delivery</small>
          </div>
          <span className="story-play">▶</span>
        </div>
        <p className="story-foot">
          Authorized media only · Owner-scoped projects · Secure sessions
        </p>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          {result ? (
            <section className="result-view">
              <span className="result-icon" aria-hidden="true">✓</span>
              <h2>{result.title}</h2>
              <p>{result.copy}</p>
              <Link className="submit-button link-button" href={result.href}>
                {result.label}
              </Link>
            </section>
          ) : (
            <>
              <div>
                <h2>{title}</h2>
                <p className="intro">{intro}</p>
              </div>
              {supportsMethods && (
                <div className="auth-methods" role="tablist" aria-label="Sign-in method">
                  {(["email", "sso"] as const).map((item) => (
                    <button
                      key={item}
                      type="button"
                      role="tab"
                      aria-selected={method === item}
                      onClick={() => {
                        setMethod(item);
                        setNotice("");
                      }}
                    >
                      Use {item === "sso" ? "SSO" : "email"}
                    </button>
                  ))}
                </div>
              )}

              {supportsMethods && method === "sso" ? (
                <div className="oauth-options">
                  {providers.map((provider) => {
                    const key = provider.name.toLowerCase();
                    const href = provider.enabled
                      ? `/v1/auth/oauth/${key}?next=${encodeURIComponent(nextPath)}`
                      : "#";
                    return (
                      <a
                        className="oauth-button"
                        aria-disabled={!provider.enabled}
                        href={href}
                        key={provider.name}
                        onClick={(event) => {
                          if (provider.enabled) return;
                          event.preventDefault();
                          setNotice(disabledProviderNotice(provider.name));
                        }}
                      >
                        <AuthProviderMark name={provider.name} />
                        Continue with {provider.name}
                      </a>
                    );
                  })}
                  <p className="switch-copy">
                    {view === "login" ? "New to Aivatar? " : "Already have an account? "}
                    <button
                      className="view-link"
                      type="button"
                      onClick={() => switchView(view === "login" ? "register" : "login")}
                    >
                      {view === "login" ? "Create an account" : "Sign in"}
                    </button>
                  </p>
                </div>
              ) : view === "login" ? (
                <form
                  className="auth-form"
                  onSubmit={(event) =>
                    submit(event, async (data) => {
                      const session = await authApi.login(
                        String(data.get("email")),
                        String(data.get("password")),
                      );
                      onAuthenticated(session);
                    })
                  }
                >
                  <label>
                    <span>Email address</span>
                    <input name="email" type="email" autoComplete="email" required placeholder="you@company.com" />
                  </label>
                  <label>
                    <span>Password</span>
                    <input name="password" type="password" autoComplete="current-password" required />
                  </label>
                  <div className="form-meta">
                    <label className="check"><input type="checkbox" defaultChecked />Keep me signed in</label>
                    <button className="view-link" type="button" onClick={() => switchView("forgot")}>Forgot password?</button>
                  </div>
                  <button className="submit-button" type="submit" disabled={busy}>Sign in</button>
                  <p className="switch-copy">New to Aivatar? <button className="view-link" type="button" onClick={() => switchView("register")}>Create an account</button></p>
                </form>
              ) : view === "register" ? (
                <form
                  className="auth-form"
                  onSubmit={(event) =>
                    submit(event, async (data) => {
                      const response = await authApi.register(
                        String(data.get("display_name")),
                        String(data.get("email")),
                        String(data.get("password")),
                      );
                      setResult({
                        title: response.debug_url ? "Verify your email" : "Check your email",
                        copy: response.debug_url
                          ? "Email sending is not configured on this environment. Continue to activate your workspace."
                          : response.message,
                        label: response.debug_url ? "Verify email" : "Return to sign in",
                        href: response.debug_url ?? "/",
                      });
                    })
                  }
                >
                  <label><span>Full name</span><input name="display_name" autoComplete="name" required maxLength={120} placeholder="Your name" /></label>
                  <label><span>Email address</span><input name="email" type="email" autoComplete="email" required placeholder="you@company.com" /></label>
                  <label><span>Password</span><input name="password" type="password" autoComplete="new-password" minLength={12} required /><small>Use at least 12 characters.</small></label>
                  <label className="check terms"><input name="terms" type="checkbox" required />I agree to use only media I own or am authorized to use.</label>
                  <button className="submit-button" type="submit" disabled={busy}>Create account</button>
                  <p className="switch-copy">Already have an account? <button className="view-link" type="button" onClick={() => switchView("login")}>Sign in</button></p>
                </form>
              ) : view === "forgot" ? (
                <form
                  className="auth-form"
                  onSubmit={(event) =>
                    submit(event, async (data) => {
                      const response = await authApi.forgotPassword(String(data.get("email")));
                      setResult({
                        title: response.debug_url ? "Reset your password" : "Check your inbox",
                        copy: response.debug_url
                          ? "Email sending is not configured on this environment. Continue to choose a new password."
                          : response.message,
                        label: response.debug_url ? "Reset password" : "Return to sign in",
                        href: response.debug_url ?? "/",
                      });
                    })
                  }
                >
                  <label><span>Email address</span><input name="email" type="email" autoComplete="email" required placeholder="you@company.com" /></label>
                  <button className="submit-button" type="submit" disabled={busy}>Send reset link</button>
                  <p className="switch-copy"><button className="view-link" type="button" onClick={() => switchView("login")}>Back to sign in</button></p>
                </form>
              ) : view === "reset" ? (
                <form
                  className="auth-form"
                  onSubmit={(event) =>
                    submit(event, async (data) => {
                      const password = String(data.get("password"));
                      if (password !== String(data.get("confirm_password"))) {
                        throw new ApiError(400, "Passwords do not match.");
                      }
                      onAuthenticated(await authApi.resetPassword(token, password));
                    })
                  }
                >
                  <label><span>New password</span><input name="password" type="password" autoComplete="new-password" minLength={12} required /></label>
                  <label><span>Confirm password</span><input name="confirm_password" type="password" autoComplete="new-password" minLength={12} required /></label>
                  <button className="submit-button" type="submit" disabled={busy}>Update password</button>
                </form>
              ) : (
                <div className="auth-loading" aria-busy={busy}>Verifying secure link…</div>
              )}
            </>
          )}
          <p className="auth-notice" role="status" aria-live="polite">{notice}</p>
        </div>
        <p className="auth-footer">
          Protected by secure, expiring sessions. Your password is never stored in plain text.
        </p>
      </section>
    </main>
  );
}
