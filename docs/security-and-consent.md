# Security and Consent

## Required production controls

- Replace development API-key/header ownership with OIDC/JWT verification and tenant-scoped DB
  queries.
- Persist immutable consent records for each avatar and voice, including grantor, subject, scope,
  time, evidence, expiry/revocation, and output policy.
- Refuse voice cloning and real-person imitation without documented permission. Do not use client
  voice samples as logs, fixtures, or general cache entries.
- Validate MIME by content, extension, size, dimensions, duration, codec, frame/sample rate, and
  decompression limits. Virus-scan uploads and isolate parsing.
- Use per-tenant object prefixes/KMS keys, short signed URLs, private buckets, retention/deletion,
  and audit records.
- Store secrets in a secret manager; never images, Compose files, source, URLs, or logs.
- Apply request/body limits, distributed rate limiting, queue quotas, egress allowlists, dependency
  scanning/SBOM, signed images, and least-privilege worker identities.
- Redact tokens, credentials, voice samples, sensitive prompts, and signed URLs. Structured logs
  should contain IDs and hashes, not private media.

## Responsible output

AI-generated output must be labeled or carry provenance/watermark metadata when required by law,
platform, or client policy. The operator must prevent deceptive impersonation and maintain a report
and takedown process. Face enhancement must not change identity.

## Current implementation status

| Control | Status |
| --- | --- |
| Strict file/path and schema controls | PARTIAL/VERIFIED in covered code paths. |
| Owner-scoped in-memory records | VERIFIED for development; not production auth. |
| Optional API key and rate limiting | VERIFIED for single process; not distributed. |
| Structured redaction processor | IMPLEMENTED; operational review required. |
| Consent schema and production-mode request enforcement | IMPLEMENTED; independent evidence verification and durable registry remain. |
| S3 isolation/KMS/signed URLs | NOT IMPLEMENTED. |
| OIDC/JWT, PostgreSQL row ownership | NOT IMPLEMENTED. |
| Dependency/image scanning | Documented; CI NOT IMPLEMENTED. |
