# Authentication deployment

Aivatar uses its own FastAPI authentication layer. Users and opaque sessions are stored in
PostgreSQL, passwords are hashed with Argon2id, verification and reset links are sent through
Resend, and Google/Apple identities are linked to the same user records.

## Local setup

The development defaults use `artifacts/auth.db` through SQLite and automatically create the
schema. Copy `.env.example` to `.env`, keep `AUTH_AUTO_MIGRATE=true`, then start both runtimes:

```bash
PROVIDER_MODE=mock uvicorn src.api.main:app --host 127.0.0.1 --port 8001

# second terminal
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. Next.js proxies `/v1`, `/health`, `/ready`, and `/metrics` to
FastAPI, so the browser receives the HttpOnly cookie from the frontend origin.

When Resend is not configured, registration and recovery responses include a one-time action URL
so the same browser can finish verification. After `RESEND_API_KEY` is set, those URLs are omitted
and only the emailed link works.

## Neon

1. Create a Neon project and copy its pooled PostgreSQL connection string.
2. Set `DATABASE_URL` to that string in the migration environment and in Vercel.
3. Run migrations once from a trusted workstation or CI job:

```bash
AUTH_AUTO_MIGRATE=false DATABASE_URL='postgresql://...' alembic upgrade head
```

Set `AUTH_AUTO_MIGRATE=false` in Vercel. Migrations must not run during serverless cold starts.

## Resend

Verify the sending domain in Resend, then configure:

```dotenv
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=Aivatar <auth@example.com>
APP_BASE_URL=https://app.example.com
```

## Google

Create a Web OAuth client. Authorized JavaScript origins:

```text
https://aivatar-staging.vercel.app
https://aivatar-web.vercel.app
http://localhost:3000
```

Authorized redirect URIs:

```text
https://aivatar-staging.vercel.app/v1/auth/oauth/google/callback
https://aivatar-web.vercel.app/v1/auth/oauth/google/callback
http://localhost:3000/v1/auth/oauth/google/callback
```

Configure `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` on the FastAPI project.
Next.js owns `/v1/auth/oauth/google` and `/v1/auth/oauth/google/callback` so the browser follows
the Google redirect and receives the session cookie on the frontend host.

## Sign in with Apple

Create an Apple Services ID, enable Sign in with Apple, and register the HTTPS return URLs:

```text
https://aivatar-staging.vercel.app/v1/auth/oauth/apple/callback
https://aivatar-web.vercel.app/v1/auth/oauth/apple/callback
```

Configure `APPLE_CLIENT_ID` with the Services ID, plus `APPLE_TEAM_ID`, `APPLE_KEY_ID`, and
`APPLE_PRIVATE_KEY` on the FastAPI project. Next.js owns `/v1/auth/oauth/apple` and both GET and
POST `/v1/auth/oauth/apple/callback`. Store the PKCS8 private key only in the deployment secret
store. A one-line environment value may use literal `\n` separators.

Apple web return URLs must use a registered HTTPS domain; Apple SSO cannot use a plain localhost
callback. Test it through the Vercel URL. Google can use
`http://localhost:3000/v1/auth/oauth/google/callback`.

Optional `AUTH_CALLBACK_URL` overrides the public origin used in `redirect_uri` when it should
differ from `APP_BASE_URL`. Leave it empty in normal staging deploys.

## Vercel security settings

```dotenv
APP_ENV=production
APP_BASE_URL=https://app.example.com
AUTH_REQUIRED=true
AUTH_AUTO_MIGRATE=false
SESSION_COOKIE_SECURE=true
ALLOWED_ORIGINS=https://app.example.com
```

Browser requests use an HttpOnly session cookie and a rotating CSRF token. The authenticated user
ID is the project owner ID; browsers cannot choose an owner with `X-Owner-Id`. Server-to-server
clients may use the configured `API_KEY` together with an explicit `X-Owner-Id`.

Before launch, verify registration, email delivery, reset-token expiry/reuse, Google and Apple
callbacks, logout, and access denial after session revocation.
