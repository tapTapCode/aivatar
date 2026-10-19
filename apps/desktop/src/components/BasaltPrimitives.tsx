import type { ReactNode } from "react";

type BannerTone = "info" | "success" | "warning";

export function BasaltBanner({ tone = "info", title, children, action }: { tone?: BannerTone; title: string; children: ReactNode; action?: ReactNode }) {
  return <aside className={`basalt-banner basalt-banner-${tone}`} role="note">
    <span className="basalt-banner-mark" aria-hidden="true" />
    <div className="basalt-banner-copy"><strong>{title}</strong><span>{children}</span></div>
    {action ? <div className="basalt-banner-action">{action}</div> : null}
  </aside>;
}

export function BasaltInline({ label, children }: { label: string; children: ReactNode }) {
  return <div className="basalt-inline"><span>{label}</span><strong>{children}</strong></div>;
}
