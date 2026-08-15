import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoot } from "@/components/AppRoot";
import { authApi } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, authApi: { ...actual.authApi, session: vi.fn(), config: vi.fn() } };
});
vi.mock("@/components/Dashboard", () => ({
  Dashboard: ({ user }: { user: { display_name: string } }) => (
    <div>Dashboard for {user.display_name}</div>
  ),
}));
vi.mock("@/components/AuthScreen", () => ({
  AuthScreen: () => <div>Login screen</div>,
}));

describe("AppRoot", () => {
  beforeEach(() => window.history.replaceState(null, "", "/"));

  it("gates anonymous users at the login screen", async () => {
    vi.mocked(authApi.session).mockRejectedValue(new Error("unauthorized"));
    render(<AppRoot />);
    await waitFor(() => expect(screen.getByText("Login screen")).toBeInTheDocument());
  });

  it("renders the workspace for an active session", async () => {
    vi.mocked(authApi.session).mockResolvedValue({
      csrf_token: "csrf",
      user: {
        id: "user-1",
        email: "client@example.com",
        display_name: "Client User",
        role: "member",
        email_verified: true,
      },
    });
    render(<AppRoot />);
    await waitFor(() =>
      expect(screen.getByText("Dashboard for Client User")).toBeInTheDocument(),
    );
  });
});
