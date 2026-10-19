# R2 retention policy

Aivatar keeps persistent project media in Cloudflare R2 and uses local cleanup for regenerable desktop intermediates.

For production buckets, configure R2 Object Lifecycle rules by prefix rather than deleting media ad hoc from the application. Suggested starting policy:

- `projects/*/cache/` — expire after 30 days.
- temporary multipart uploads — retain Cloudflare's default automatic cleanup.
- final renders, captions, master narration, approved presenter clips, and locked assets — no automatic expiration until the team's retention policy is agreed.

Do not apply a blanket expiration rule to the entire bucket. Cloudflare lifecycle deletion is asynchronous and bucket lock rules take precedence over lifecycle rules.
