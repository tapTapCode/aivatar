"use client";

import { useCallback, useEffect, useState } from "react";
import { authApi } from "@/lib/api";
import type { Session } from "@/lib/types";
import { AuthScreen } from "@/components/AuthScreen";
import { Dashboard } from "@/components/Dashboard";

export function AppRoot() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const view = new URLSearchParams(window.location.search).get("view");
    if (view === "verify" || view === "reset") {
      queueMicrotask(() => setLoading(false));
      return;
    }
    authApi
      .session()
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setLoading(false));
  }, []);

  const signedOut = useCallback(() => {
    setSession(null);
    window.history.replaceState(null, "", "/");
  }, []);

  if (loading) {
    return (
      <main className="boot-screen" aria-busy="true">
        <span className="boot-orb" />
        <p>Opening your workspace…</p>
      </main>
    );
  }
  if (!session) return <AuthScreen onAuthenticated={setSession} />;
  return (
    <Dashboard
      user={session.user}
      csrfToken={session.csrf_token}
      onSignedOut={signedOut}
      onSessionUpdated={setSession}
    />
  );
}
