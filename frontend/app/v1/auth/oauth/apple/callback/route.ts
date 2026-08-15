import { proxyOAuthCallback } from "@/lib/oauth-proxy";

export async function GET(request: Request) {
  return proxyOAuthCallback(request, "/v1/auth/oauth/apple/callback");
}

export async function POST(request: Request) {
  return proxyOAuthCallback(request, "/v1/auth/oauth/apple/callback", {
    method: "POST",
    body: await request.text(),
  });
}
