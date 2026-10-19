import { useCallback, useState } from "react";
import type { Session } from "./lib/types";
import { Dashboard } from "./components/Dashboard";
import appStyles from "./styles.module.css";
import channelStyles from "./channel-studio.module.css";

export default function App() {
  const [session, setSession] = useState<Session>({
    user: {
      id: "local-operator",
      email: "editor@aivatar.local",
      display_name: "Local Studio",
      role: "operator",
      email_verified: true,
    },
    csrf_token: "local-csrf-token",
  });

  const signedOut = useCallback(() => {
    // Keep local session active
  }, []);

  return (
    <div className={`${appStyles.moduleAnchor} ${channelStyles.channelModuleAnchor}`}>
    <Dashboard
      user={session.user}
      csrfToken={session.csrf_token}
      onSignedOut={signedOut}
      onSessionUpdated={setSession}
    />
    </div>
  );
}
