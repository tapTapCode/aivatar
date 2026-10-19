# Aivatar commercial deployment

Channel Studio now contains the local implementation for voice previews, assisted scene direction,
licensed local music selection, selectable transitions, a workspace credit ledger, and subscription
checkout hooks.

## Local mode

Local mode is deliberately single-user. On first API start it creates a local workspace, an owner
member, and a development credit balance. It does not send invitations or create payment sessions.
Use the Channel Studio controls to preview a configured voice, suggest scene direction, choose music
from `AIVATAR_MUSIC_CATALOG_DIR`, and select a transition before rendering.

## Hosted mode checklist

Set these server-side values in the deployment secret manager, never in the browser or repository:

```dotenv
AIVATAR_AUTH_MODE=your-auth-adapter
AIVATAR_PUBLIC_BASE_URL=https://studio.example.com
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
STRIPE_CREDIT_PRICE_ID=price_...
AIVATAR_MUSIC_CATALOG_DIR=/var/lib/aivatar/music
```

The checkout endpoint is `/studio/commercial/checkout`. A production deployment still needs an
identity provider and a Stripe webhook consumer that verifies signatures and posts subscription or
credit settlements into the ledger. Until those are configured, the UI correctly reports team roles
and Stripe as unavailable.

## Deployment shape

Run the FastAPI sidecar behind HTTPS with a persistent database, object storage for media, and a
background worker for render jobs. Keep `workspace/` outside the container filesystem and restrict
the upload and preview routes to authenticated users. The local frontend can be built with
`pnpm build` and served by the deployment's static host.
