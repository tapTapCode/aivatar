/* eslint-disable @next/next/no-img-element */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthScreen } from "@/components/AuthScreen";
import { authApi } from "@/lib/api";

vi.mock("next/image", () => ({
  default: ({
    priority,
    ...props
  }: React.ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean }) => {
    void priority;
    return <img {...props} alt={props.alt ?? ""} />;
  },
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    authApi: {
      config: vi.fn(),
      login: vi.fn(),
      register: vi.fn(),
      forgotPassword: vi.fn(),
      resetPassword: vi.fn(),
      verifyEmail: vi.fn(),
    },
  };
});

describe("AuthScreen", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.mocked(authApi.config).mockResolvedValue({
      providers: [
        { name: "Google", enabled: false },
        { name: "Apple", enabled: false },
      ],
      registration_enabled: true,
      password_reset_enabled: true,
    });
  });

  it("shows only login by default and switches views", async () => {
    render(<AuthScreen onAuthenticated={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Full name")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
    expect(screen.getByLabelText("Full name")).toBeInTheDocument();
    expect(screen.queryByText("Forgot password?")).not.toBeInTheDocument();
  });

  it("explains disabled SSO providers", async () => {
    render(<AuthScreen onAuthenticated={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: "Use SSO" }));
    await userEvent.click(screen.getByRole("link", { name: /Continue with Google/ }));
    expect(screen.getByText(/Google SSO needs OAuth credentials/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: /Continue with Apple/ }));
    expect(screen.getByText(/Apple sign-in is paused/)).toBeInTheDocument();
  });

  it("links enabled SSO providers and explains callback errors", async () => {
    window.history.replaceState(null, "", "/?error=oauth_state&method=sso");
    vi.mocked(authApi.config).mockResolvedValue({
      providers: [
        { name: "Google", enabled: true },
        { name: "Apple", enabled: true },
      ],
      registration_enabled: true,
      password_reset_enabled: true,
    });
    render(<AuthScreen onAuthenticated={vi.fn()} />);
    expect(
      await screen.findByText("Social sign-in expired. Start again from this page."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Continue with Google/ })).toHaveAttribute(
      "href",
      "/v1/auth/oauth/google?next=%2F",
    );
    expect(screen.getByRole("link", { name: /Continue with Apple/ })).toHaveAttribute(
      "href",
      "/v1/auth/oauth/apple?next=%2F",
    );
  });

  it("submits registration and recovery results", async () => {
    vi.mocked(authApi.register).mockResolvedValue({
      message: "Check your email to verify your account.",
      debug_url: "/?view=verify&token=local",
    });
    render(<AuthScreen onAuthenticated={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Create an account" }));
    fireEvent.change(screen.getAllByLabelText("Full name")[0], { target: { value: "Client User" } });
    fireEvent.change(screen.getAllByLabelText("Email address")[0], { target: { value: "client@example.com" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "correct horse battery" } });
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Verify your email" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Verify email" })).toHaveAttribute("href", "/?view=verify&token=local");
  });
});
