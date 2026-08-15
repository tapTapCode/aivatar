import { proxyOAuthCallback } from "@/lib/oauth-proxy";

export async function GET(request: Request) {
  return proxyOAuthCallback(request, "/v1/auth/oauth/google/callback");
}
