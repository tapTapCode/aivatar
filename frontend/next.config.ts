import type { NextConfig } from "next";

const apiOrigin = (
  process.env.FASTAPI_ORIGIN ??
  (process.env.VERCEL ? "https://aivatar-api-staging.vercel.app" : "http://127.0.0.1:8001")
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/v1/:path*", destination: `${apiOrigin}/v1/:path*` },
      { source: "/health", destination: `${apiOrigin}/health` },
      { source: "/ready", destination: `${apiOrigin}/ready` },
      { source: "/metrics", destination: `${apiOrigin}/metrics` },
    ];
  },
};

export default nextConfig;
