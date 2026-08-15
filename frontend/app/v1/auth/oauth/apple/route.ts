import { proxyOAuthStart } from "@/lib/oauth-proxy";

export async function GET(request: Request) {
  return proxyOAuthStart(request, "/v1/auth/oauth/apple");
}
