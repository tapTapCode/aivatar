import { describe, expect, it } from "vitest";
import { resolveFrontendLocation } from "@/lib/oauth-proxy";

describe("resolveFrontendLocation", () => {
  it("keeps relative OAuth redirects on the frontend origin", () => {
    expect(
      resolveFrontendLocation(
        "https://aivatar-staging.vercel.app/v1/auth/oauth/google/callback",
        "/?error=oauth_state",
      ),
    ).toBe("https://aivatar-staging.vercel.app/?error=oauth_state");
  });

  it("preserves absolute provider or app URLs", () => {
    expect(
      resolveFrontendLocation(
        "https://aivatar-staging.vercel.app/v1/auth/oauth/google",
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=x",
      ),
    ).toBe("https://accounts.google.com/o/oauth2/v2/auth?client_id=x");
  });
});
