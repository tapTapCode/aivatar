const DEFAULT_API_ORIGIN = process.env.VERCEL
  ? "https://aivatar-api-staging.vercel.app"
  : "http://127.0.0.1:8001";

export function apiOrigin(): string {
  return (process.env.FASTAPI_ORIGIN ?? DEFAULT_API_ORIGIN).replace(/\/$/, "");
}

export function resolveFrontendLocation(requestUrl: string, location: string): string {
  if (/^https?:\/\//i.test(location)) {
    return location;
  }
  return new URL(location, requestUrl).toString();
}

export async function proxyOAuthStart(request: Request, path: string): Promise<Response> {
  const incoming = new URL(request.url);
  const upstream = await fetch(`${apiOrigin()}${path}${incoming.search}`, {
    method: "GET",
    redirect: "manual",
    headers: { cookie: request.headers.get("cookie") ?? "" },
  });
  if (upstream.status === 503) {
    return Response.redirect(new URL("/?error=oauth_paused&method=sso", request.url), 303);
  }
  const location = resolveFrontendLocation(
    request.url,
    upstream.headers.get("location") ?? "/?error=oauth_failed&method=sso",
  );
  const status = upstream.status >= 300 && upstream.status < 400 ? upstream.status : 303;
  return new Response(null, { status, headers: { location } });
}

export async function proxyOAuthCallback(
  request: Request,
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const incoming = new URL(request.url);
  const upstream = await fetch(`${apiOrigin()}${path}${incoming.search}`, {
    method: init?.method ?? request.method,
    redirect: "manual",
    headers: {
      cookie: request.headers.get("cookie") ?? "",
      "content-type": request.headers.get("content-type") ?? "",
    },
    body: init?.body,
  });
  const location = resolveFrontendLocation(
    request.url,
    upstream.headers.get("location") ?? "/",
  );
  const headers = new Headers({ location });
  for (const cookie of upstream.headers.getSetCookie()) {
    headers.append("set-cookie", cookie);
  }
  return new Response(null, { status: 303, headers });
}
