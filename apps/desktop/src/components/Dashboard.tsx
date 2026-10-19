


import {
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChannelStudio } from "./ChannelStudio";
import { BaseTabs } from "./BaseControls";
import { BasaltBanner } from "./BasaltPrimitives";
import { ApiError, authApi, loadWorkspace, workspaceApi } from "../lib/api";
import { STUDIO_PRESETS, TEMPLATES, WORKFLOWS, type StudioMode, type StudioPreset } from "../lib/studio";
import { requestOnboardingTour } from "./OnboardingTour";
import type {
  AuthUser,
  HeyGenCatalog,
  MediaItem,
  Project,
  Session,
  VideoJob,
  WorkspaceData,
} from "../lib/types";

type Route =
  | "channel-studio"
  | "overview"
  | "studio"
  | "projects"
  | "assets"
  | "templates"
  | "tools"
  | "videos"
  | "settings";

const ROUTE_PATHS: Record<Route, string> = {
  "channel-studio": "/channel-studio",
  overview: "/",
  studio: "/create",
  projects: "/projects",
  videos: "/videos",
  assets: "/assets",
  templates: "/templates",
  tools: "/tools",
  settings: "/settings",
};

function routeState(pathname: string): { route: Route; mode: StudioMode; videoId: string | null } {
  const parts = pathname.split("/").filter(Boolean).map((part) => decodeURIComponent(part));
  const [section, value] = parts;
  if (section === "create") {
    const mode = value && value in STUDIO_PRESETS ? value as StudioMode : "avatar";
    return { route: "studio", mode, videoId: null };
  }
  if (section === "videos") return { route: "videos", mode: "avatar", videoId: value || null };
  if (["channel-studio", "projects", "assets", "templates", "tools", "settings"].includes(section)) {
    return { route: section as Route, mode: "avatar", videoId: null };
  }
  return { route: "overview", mode: "avatar", videoId: null };
}

function pushRoute(path: string) {
  if (window.location.pathname !== path) window.history.pushState({}, "", path);
}

const EMPTY_COSTS = {
  estimated_usd: 0,
  actual_usd: 0,
  job_count: 0,
  completed_count: 0,
  failed_count: 0,
  projects: [],
  gpu_hourly_rate_usd: 0.22,
  billing_policy: "Presenter, voice, visual, and GPU costs are tracked per provider and render.",
  heygen_engine: "avatar_iv",
  heygen_rate_usd_per_minute: 4,
  proof_replay_job_count: 0,
  gpu_job_count: 0,
  heygen_job_count: 0,
  heygen_estimated_usd: 0,
  heygen_actual_usd: 0,
  proof_replay_usd: 0,
  gpu_estimated_usd: 0,
  gpu_actual_usd: 0,
};

const EMPTY_DATA: WorkspaceData = {
  health: "unknown",
  ready: "unknown",
  projects: [],
  jobs: [],
  metrics: "",
  media: [],
  costs: EMPTY_COSTS,
};

function money(value?: number | null) {
  if (value == null) return "—";
  return `$${value.toFixed(2)}`;
}

const STAGES = [
  "PENDING",
  "VALIDATING",
  "QUEUED",
  "DOWNLOADING_MODELS",
  "PREPROCESSING",
  "GENERATING_AUDIO",
  "GENERATING_AVATAR",
  "GENERATING_VISUAL",
  "LIP_SYNCING",
  "RENDERING_SCENE",
  "ASSEMBLING_TIMELINE",
  "VALIDATING_OUTPUT",
  "UPLOADING",
  "COMPLETED",
];

const SEEN_KEY = "aivatar.notifications.seenAt";

const COMMANDS: Array<{ title: string; detail: string; route: Route; icon: IconName }> = [
  { title: "Create an avatar video", detail: "Open the presenter workflow", route: "studio", icon: "avatar" },
  { title: "Review video jobs", detail: "Track renders and downloads", route: "videos", icon: "play" },
  { title: "Browse projects", detail: "Continue a production", route: "projects", icon: "folder" },
  { title: "Open assets", detail: "Review authorized media", route: "assets", icon: "image" },
  { title: "Explore templates", detail: "Start with a format", route: "templates", icon: "slides" },
  { title: "AI tools", detail: "Choose a focused workflow", route: "tools", icon: "spark" },
  { title: "Workspace settings", detail: "Review runtime health", route: "settings", icon: "settings" },
];

type IconName =
  | "plus"
  | "video"
  | "avatar"
  | "image"
  | "slides"
  | "spark"
  | "play"
  | "folder"
  | "upload"
  | "settings"
  | "search"
  | "menu"
  | "bell"
  | "logout"
  | "help"
  | "home"
  | "more"
  | "close"
  | "trash"
  | "check";

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    plus: <path d="M12 5v14M5 12h14" />,
    video: <><rect x="3" y="5" width="13" height="14" rx="2" /><path d="m16 10 5-3v10l-5-3z" /></>,
    avatar: <><circle cx="12" cy="8" r="3" /><path d="M5 21c.8-4 3-6 7-6s6.2 2 7 6" /></>,
    image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 15-5-5L5 20" /></>,
    slides: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    spark: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z" /></>,
    play: <path d="m9 5 10 7-10 7z" />,
    folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
    upload: <path d="M12 16V4m0 0L8 8m4-4 4 4M5 20h14" />,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.55V20.3h-3v-.09A1.7 1.7 0 0 0 10.66 18.66a1.7 1.7 0 0 0-1.88.34l-.06.06L6.6 16.94l.06-.06A1.7 1.7 0 0 0 7 15a1.7 1.7 0 0 0-1.55-1.04h-.09v-3h.09A1.7 1.7 0 0 0 7 9.92a1.7 1.7 0 0 0-.34-1.88l-.06-.06L8.72 5.86l.06.06A1.7 1.7 0 0 0 10.66 6.26a1.7 1.7 0 0 0 1.04-1.55v-.09h3v.09a1.7 1.7 0 0 0 1.04 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.55 1.04h.09v3h-.09A1.7 1.7 0 0 0 19.4 15Z" /></>,
    search: <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></>,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" /><path d="M10 21h4" /></>,
    logout: <><path d="M10 5H5v14h5" /><path d="m14 8 4 4-4 4M8 12h10" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 4.35 1.67c-.98.98-1.85 1.34-1.85 2.83M12 17h.01" /></>,
    home: <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    trash: <><path d="M4 7h16M9 7V5h6v2M8 7l1 13h6l1-13" /></>,
    check: <path d="m5 12 4 4 10-10" />,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

function badgeClass(state: string) {
  if (state === "COMPLETED") return "ok";
  if (["FAILED", "CANCELLED"].includes(state)) return "fail";
  if (["QUEUED", "PENDING"].includes(state)) return "wait";
  return "run";
}

function PageHeader({
  eyebrow,
  title,
  copy,
  children,
}: {
  eyebrow: string;
  title: string;
  copy: string;
  children?: ReactNode;
}) {
  return (
    <section className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="lede">{copy}</p>
      </div>
      {children}
    </section>
  );
}

function SectionHeading({
  title,
  copy,
  children,
}: {
  title: string;
  copy?: string;
  children?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div><h2>{title}</h2>{copy && <p>{copy}</p>}</div>
      {children}
    </div>
  );
}

function ToolCard({
  title,
  copy,
  icon,
  featured,
  onClick,
}: {
  title: string;
  copy: string;
  icon: IconName;
  featured?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className={`tool-card${featured ? " featured" : ""}`} onClick={onClick}>
      <span className="tool-icon"><Icon name={icon} /></span>
      {featured && <span className="orb" aria-hidden="true" />}
      <h3>{title}</h3><p>{copy}</p>
    </button>
  );
}

function TemplateCard({
  template,
  onSelect,
}: {
  template: (typeof TEMPLATES)[number];
  onSelect: () => void;
}) {
  return (
    <button type="button" className="template-card" onClick={onSelect}>
      <div className={`template-thumb ${template.thumb}`}>
        <span className="thumb-chip">{template.aspect}</span>
        <span className="favorite" aria-hidden="true"><Icon name="more" /></span>
      </div>
      <div className="template-meta">
        <div><strong>{template.title}</strong><span>{template.kind}</span></div>
        <span className="tiny">{template.aspect}</span>
      </div>
    </button>
  );
}

function isPresenterVideo(item: MediaItem) {
  return (
    (item.content_type ?? "").startsWith("video/") ||
    /\.(mp4|mov|webm)$/i.test(item.original_filename)
  );
}

function presenterKind(item: MediaItem) {
  if (item.content_type === "application/json") return "HeyGen avatar";
  if (isPresenterVideo(item)) return "imported video";
  return "unused still";
}

function MediaThumb({ item }: { item: MediaItem }) {
  return (
    <div className={`project-thumb ${item.kind === "voice" ? "thumb-talk" : "thumb-video"}`}>
      <span className="thumb-chip">
        {item.kind === "presenter" ? presenterKind(item) : item.kind}
      </span>
    </div>
  );
}

function jobNotice(job: VideoJob) {
  if (job.state === "COMPLETED") return { title: "Video is ready", tone: "ok" as const };
  if (job.state === "FAILED") return { title: "Render failed", tone: "error" as const };
  if (job.state === "CANCELLED") return { title: "Job cancelled", tone: "error" as const };
  return { title: "Render in progress", tone: "ok" as const };
}

function ProjectCard({ item, onOpen }: { item: VideoJob; onOpen: () => void }) {
  const complete = item.state === "COMPLETED";
  return (
    <button type="button" className="project-card" onClick={onOpen}>
      <div className="project-thumb">
        <span className="thumb-chip">{item.watermark_status === "CLEAN_AUTHORIZED" ? "Clean export" : "Video"}</span>
        {complete && <span className="play"><Icon name="play" /></span>}
      </div>
      <div className="project-title"><strong>{item.project_id}</strong><span className="icon-btn"><Icon name="more" /></span></div>
      <small>{complete ? "Ready to review" : item.state.replaceAll("_", " ")} · {new Date(item.updated_at).toLocaleDateString()}</small>
    </button>
  );
}

function outputFor(aspect: string, shortEdge: number) {
  const sizes: Record<string, { width: number; height: number }> = {
    "16:9": { width: Math.round((shortEdge * 16) / 9 / 2) * 2, height: shortEdge },
    "9:16": { width: shortEdge, height: Math.round((shortEdge * 16) / 9 / 2) * 2 },
    "1:1": { width: shortEdge, height: shortEdge },
    "4:5": { width: shortEdge, height: Math.round((shortEdge * 5) / 4 / 2) * 2 },
  };
  return sizes[aspect];
}

export function Dashboard({
  user,
  csrfToken,
  onSignedOut,
  onSessionUpdated,
}: {
  user: AuthUser;
  csrfToken: string;
  onSignedOut: () => void;
  onSessionUpdated?: (session: Session) => void;
}) {
  const initialRoute = routeState(window.location.pathname);
  const [route, setRoute] = useState<Route>(initialRoute.route);
  const [data, setData] = useState(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [alert, setAlert] = useState<{ message: string; kind: "" | "ok" | "error" }>({ message: "", kind: "" });
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(initialRoute.videoId);
  const [navOpen, setNavOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [studioMode, setStudioMode] = useState<StudioMode>(initialRoute.mode);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [seenAt, setSeenAt] = useState(() => {
    try {
      return Number(window.localStorage?.getItem(SEEN_KEY) || 0);
    } catch {
      return 0;
    }
  });
  const commandInput = useRef<HTMLInputElement>(null);

  const reportError = useCallback((error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      onSignedOut();
      return;
    }
    setAlert({ message: error instanceof Error ? error.message : String(error), kind: "error" });
  }, [onSignedOut]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loadWorkspace(csrfToken));
      setAlert((current) => (current.kind === "ok" ? current : { message: "", kind: "" }));
    } catch (error) {
      reportError(error);
    } finally {
      setLoading(false);
    }
  }, [csrfToken, reportError]);

  useEffect(() => {
    queueMicrotask(() => void refresh());
  }, [refresh]);
  useEffect(() => {
    const active = data.jobs.some((job) => !["COMPLETED", "FAILED", "CANCELLED"].includes(job.state));
    if (!active) return;
    const timer = window.setInterval(() => { void refresh(); }, 4000);
    return () => window.clearInterval(timer);
  }, [data.jobs, refresh]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
        window.setTimeout(() => commandInput.current?.focus(), 0);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      const next = routeState(window.location.pathname);
      setRoute(next.route);
      setStudioMode(next.mode);
      setSelectedVideoId(next.videoId);
      setNavOpen(false);
      setNotifyOpen(false);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function go(next: Route) {
    pushRoute(ROUTE_PATHS[next]);
    setRoute(next);
    if (next !== "videos") setSelectedVideoId(null);
    setNavOpen(false);
    setNotifyOpen(false);
  }

  function openStudio(mode: StudioMode = "avatar") {
    pushRoute(`/create/${mode}`);
    setStudioMode(mode);
    setRoute("studio");
    setNavOpen(false);
    setNotifyOpen(false);
  }

  function openVideo(videoId: string) {
    pushRoute(`/videos/${encodeURIComponent(videoId)}`);
    setSelectedVideoId(videoId);
    setRoute("videos");
    setNotifyOpen(false);
  }

  const notices = useMemo(
    () =>
      [...data.jobs]
        .sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))
        .slice(0, 8),
    [data.jobs],
  );
  const unread = notices.filter((job) => +new Date(job.updated_at) > seenAt).length;

  function markNoticesRead() {
    const now = Date.now();
    setSeenAt(now);
    try {
      window.localStorage?.setItem(SEEN_KEY, String(now));
    } catch {
      /* ignore */
    }
  }

  async function logout() {
    try {
      await authApi.logout(csrfToken);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) reportError(error);
    } finally {
      onSignedOut();
    }
  }

  const initials = user.display_name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  const nav = [
    ["overview", "Home", "home"],
    ["studio", "Create", "plus"],
    ["projects", "Projects", "folder"],
    ["videos", "Videos", "play"],
    ["channel-studio", "Channel Studio", "spark"],
    ["assets", "Assets", "image"],
    ["templates", "Templates", "slides"],
    ["tools", "AI tools", "spark"],
  ] as Array<[Route, string, IconName]>;

  return (
    <div className={navOpen ? "nav-open" : ""}>
      <a className="skip-link" href="#main">Skip to content</a>
      {navOpen && <button className="nav-backdrop" type="button" aria-label="Close navigation" onClick={() => setNavOpen(false)} />}
      <div className="app-shell" data-tour="workspace">
        <aside className="sidebar" aria-label="Primary navigation">
          <div className="brand-row">
            <button className="brand" type="button" onClick={() => go("overview")} aria-label="Aivatar home">
              <img className="brand-logo" src="/logo-aivatar.png" alt="Aivatar" />
            </button>
            <button className="icon-btn sidebar-toggle" type="button" aria-label="Collapse navigation" onClick={() => setNavOpen(false)}><Icon name="close" /></button>
          </div>
          <nav className="nav-groups" data-tour="navigation">
            <div className="nav-group">
              <p className="nav-label">Workspace</p>
              {nav.slice(0, 4).map(([key, label, icon]) => (
                <button key={key} type="button" className={`nav-link${route === key ? " is-active" : ""}`} onClick={() => key === "studio" ? openStudio(studioMode) : go(key)}><Icon name={icon} /><span>{label}</span></button>
              ))}
            </div>
            <div className="nav-group">
              <p className="nav-label">Create with AI</p>
              {nav.slice(4).map(([key, label, icon]) => (
                <button key={key} type="button" className={`nav-link${route === key ? " is-active" : ""}`} onClick={() => go(key)}><Icon name={icon} /><span>{label}</span></button>
              ))}
            </div>
          </nav>
          <div className="sidebar-footer">
            <button type="button" className={`nav-link${route === "settings" ? " is-active" : ""}`} onClick={() => go("settings")}><Icon name="settings" /><span>Settings</span></button>
            <button type="button" className="nav-link" data-tour="help" onClick={() => { setHelpOpen(true); setNavOpen(false); }}><Icon name="help" /><span>Help</span></button>
            <div className="workspace-card">
              <span className="avatar" aria-hidden="true">{initials}</span>
              <span className="workspace-user"><strong>{user.display_name}</strong><small>{user.email}</small></span>
              <span className="status-dot" title="API status" />
            </div>
            <button type="button" className="nav-link" onClick={() => void logout()}><Icon name="logout" /><span>Sign out</span></button>
            <p className="runtime-status">{loading ? "Checking workspace…" : `API ${data.health} · runtime ${data.ready}`}</p>
          </div>
        </aside>
        <main id="main" className="main-content">
          <header className="topbar">
            <button className="mobile-menu icon-btn" type="button" aria-label="Open navigation" onClick={() => setNavOpen(true)}><Icon name="menu" /></button>
            <button className="command-trigger" type="button" onClick={() => { setCommandOpen(true); window.setTimeout(() => commandInput.current?.focus(), 0); }}>
              <Icon name="search" /><span>Search projects, templates, and tools</span><kbd>⌘ K</kbd>
            </button>
            <div className="topbar-actions">
              <div className="notify-wrap">
                <button
                  className="icon-btn notification-btn"
                  type="button"
                  aria-label={unread ? `${unread} unread notifications` : "Notifications"}
                  aria-expanded={notifyOpen}
                  onClick={() => {
                    setNotifyOpen((open) => !open);
                    if (!notifyOpen) markNoticesRead();
                  }}
                >
                  <Icon name="bell" />
                  {unread > 0 && <span className="notify-dot">{unread}</span>}
                </button>
                {notifyOpen && (
                  <div className="notify-panel" role="dialog" aria-label="Notifications">
                    <div className="notify-head"><strong>Activity</strong><button className="text-button" type="button" onClick={() => setNotifyOpen(false)}>Close</button></div>
                    {notices.length ? notices.map((job) => {
                      const notice = jobNotice(job);
                      return (
                        <button className="notify-item" type="button" key={job.video_id} onClick={() => openVideo(job.video_id)}>
                          <span className={`badge ${badgeClass(job.state)}`}>{notice.title}</span>
                          <small>{job.project_id} · {new Date(job.updated_at).toLocaleString()}</small>
                        </button>
                      );
                    }) : <p className="muted tiny">No production activity yet. Queue a render to see updates here.</p>}
                  </div>
                )}
              </div>
              <button type="button" className="btn primary" data-tour="create" onClick={() => setCreateOpen(true)}><Icon name="plus" /><span>Create</span></button>
            </div>
          </header>
          {alert.message && <div className={`alert ${alert.kind}`} role="status">{alert.message}</div>}
          <div className="view" aria-live="polite">
            <DashboardView
              route={route}
              data={data}
              loading={loading}
              user={user}
              csrfToken={csrfToken}
              selectedVideoId={selectedVideoId}
              go={go}
              openStudio={openStudio}
              studioMode={studioMode}
              openVideo={openVideo}
              refresh={refresh}
              showAlert={(message, kind = "ok") => setAlert({ message, kind })}
              reportError={reportError}
              onSessionUpdated={onSessionUpdated}
            />
          </div>
        </main>
      </div>
      {createOpen && (
        <dialog className="script-dialog" open aria-labelledby="create-title">
          <form onSubmit={(event) => event.preventDefault()}>
            <button className="dialog-close icon-btn" type="button" onClick={() => setCreateOpen(false)} aria-label="Close"><Icon name="close" /></button>
            <p className="eyebrow">New project</p>
            <h2 id="create-title">Choose a starting format</h2>
            <p className="muted">Each option opens a real studio preset with the right aspect, captions, and scene type.</p>
            <div className="create-choice-list">
              {WORKFLOWS.map((item) => (
                <button className="command-item" type="button" key={item.id} onClick={() => { setCreateOpen(false); openStudio(item.id); }}>
                  <Icon name={item.icon} /><span><strong>{item.title}</strong><small>{item.copy}</small></span>
                </button>
              ))}
            </div>
          </form>
        </dialog>
      )}
      {helpOpen && (
        <dialog className="script-dialog" open aria-labelledby="help-title">
          <form onSubmit={(event) => event.preventDefault()}>
            <button className="dialog-close icon-btn" type="button" onClick={() => setHelpOpen(false)} aria-label="Close"><Icon name="close" /></button>
            <p className="eyebrow">Help</p>
            <h2 id="help-title">How Aivatar works</h2>
            <ol className="help-steps">
              <li><strong>Choose a format.</strong> Each preset selects the presenter and visual workflow it needs.</li>
              <li><strong>Add the required inputs.</strong> Presenter formats need an authorized avatar; visual formats need a visual direction.</li>
              <li><strong>Review and approve.</strong> Aivatar plans scenes, generates approved media, and assembles the MP4.</li>
              <li><strong>Review the result.</strong> Download the completed export and inspect its render status and cost.</li>
            </ol>
            <p className="muted tiny">Private team studio. Provider credentials stay server-side; browser-inspection bypasses are not used.</p>
            <div className="dialog-actions"><button type="button" className="btn secondary" onClick={() => { setHelpOpen(false); window.setTimeout(requestOnboardingTour, 150); }}>Restart tour</button><button type="button" className="btn primary" onClick={() => setHelpOpen(false)}>Got it</button></div>
          </form>
        </dialog>
      )}
      {commandOpen && (
        <dialog className="command-dialog" open aria-labelledby="command-title">
          <form method="dialog" onSubmit={(event) => event.preventDefault()}>
            <label className="command-search"><Icon name="search" /><input ref={commandInput} type="search" value={commandQuery} onChange={(event) => setCommandQuery(event.target.value)} placeholder="Search anything" autoComplete="off" /><button className="icon-btn" type="button" onClick={() => setCommandOpen(false)} aria-label="Close"><Icon name="close" /></button></label>
          </form>
          <div className="command-results" role="listbox">
            {COMMANDS.filter((item) => `${item.title} ${item.detail}`.toLowerCase().includes(commandQuery.toLowerCase())).map((item) => (
              <button className="command-item" type="button" key={item.route} onClick={() => { go(item.route); setCommandOpen(false); setCommandQuery(""); }}>
                <Icon name={item.icon} /><span><strong>{item.title}</strong><small>{item.detail}</small></span>
              </button>
            ))}
          </div>
        </dialog>
      )}
    </div>
  );
}

function DashboardView({
  route,
  data,
  loading,
  user,
  csrfToken,
  selectedVideoId,
  go,
  openStudio,
  studioMode,
  openVideo,
  refresh,
  showAlert,
  reportError,
  onSessionUpdated,
}: {
  route: Route;
  data: WorkspaceData;
  loading: boolean;
  user: AuthUser;
  csrfToken: string;
  selectedVideoId: string | null;
  go: (route: Route) => void;
  openStudio: (mode?: StudioMode) => void;
  studioMode: StudioMode;
  openVideo: (id: string) => void;
  refresh: () => Promise<void>;
  showAlert: (message: string, kind?: "ok" | "error") => void;
  reportError: (error: unknown) => void;
  onSessionUpdated?: (session: Session) => void;
}) {
  if (route === "channel-studio") return <ChannelStudio />;
  if (route === "studio") return <Studio preset={STUDIO_PRESETS[studioMode]} media={data.media} user={user} csrfToken={csrfToken} refresh={refresh} openVideo={openVideo} showAlert={showAlert} reportError={reportError} />;
  if (route === "projects") return <Projects projects={data.projects} jobs={data.jobs} openStudio={openStudio} openVideo={openVideo} csrfToken={csrfToken} refresh={refresh} showAlert={showAlert} reportError={reportError} />;
  if (route === "assets") return <Assets media={data.media} csrfToken={csrfToken} refresh={refresh} openStudio={openStudio} showAlert={showAlert} reportError={reportError} />;
  if (route === "templates") return <Templates openStudio={openStudio} showAlert={showAlert} />;
  if (route === "tools") return <Tools openStudio={openStudio} />;
  if (route === "videos") return <Videos jobs={data.jobs} selectedVideoId={selectedVideoId} csrfToken={csrfToken} refresh={refresh} reportError={reportError} showAlert={showAlert} openVideo={openVideo} openStudio={openStudio} />;
  if (route === "settings") return <Settings data={data} user={user} csrfToken={csrfToken} showAlert={showAlert} reportError={reportError} onSessionUpdated={onSessionUpdated} />;
  return <Overview jobs={data.jobs} loading={loading} go={go} openStudio={openStudio} openVideo={openVideo} />;
}

function Overview({ jobs, loading, go, openStudio, openVideo }: { jobs: VideoJob[]; loading: boolean; go: (r: Route) => void; openStudio: (mode?: StudioMode) => void; openVideo: (id: string) => void }) {
  if (loading && !jobs.length) return <div className="grid">{[0, 1, 2, 3].map((item) => <div className="skeleton" key={item} />)}</div>;
  return <>
    <PageHeader eyebrow="Private team studio" title="What would you like to make?" copy="Choose a format, review the script and visual plan, then generate through the configured presenter and media providers."><div className="header-actions"><button className="btn secondary" type="button" onClick={() => go("projects")}>View projects</button></div></PageHeader>
    <section className="basalt-overview" aria-label="Workspace overview">
      <div className="basalt-kpi"><span className="label">Total productions</span><strong>{jobs.length}</strong><span className="muted tiny">All queued and completed jobs</span></div>
      <div className="basalt-kpi"><span className="label">Completed</span><strong>{jobs.filter((job) => job.state === "COMPLETED").length}</strong><span className="muted tiny">Ready to download</span></div>
      <div className="basalt-kpi"><span className="label">In progress</span><strong>{jobs.filter((job) => ["PENDING", "QUEUED", "RUNNING"].includes(job.state)).length}</strong><span className="muted tiny">Currently rendering</span></div>
      <div className="basalt-activity"><span className="label">Latest activity</span>{jobs.length ? jobs.slice(0, 3).map((job) => <button className="basalt-activity-item" type="button" key={job.video_id} onClick={() => openVideo(job.video_id)}><span>{job.project_id}</span><b>{job.state.replaceAll("_", " ")}</b></button>) : <span className="muted tiny">Your first production will appear here.</span>}</div>
    </section>
    <BasaltBanner title="Your production system is ready" action={<button className="text-button" type="button" onClick={() => openStudio()}>Create a render →</button>}>Build from a preset, review the scene plan, then keep the final MP4 and its status in one workspace.</BasaltBanner>
    <section className="section" data-tour="create"><SectionHeading title="Create something new" copy="Each card opens a studio preset with the matching format already selected." /><div className="create-grid">
      {WORKFLOWS.map((item) => (
        <ToolCard key={item.id} title={item.eyebrow} copy={item.copy} icon={item.icon} featured={item.featured} onClick={() => openStudio(item.id)} />
      ))}
    </div></section>
    <section className="section" data-tour="templates"><SectionHeading title="Recommended templates" copy="Reusable starting points for your next production."><button className="text-button" type="button" onClick={() => go("templates")}>Browse all</button></SectionHeading><div className="template-rail">{TEMPLATES.map((template) => <TemplateCard key={template.title} template={template} onSelect={() => openStudio(template.id)} />)}</div></section>
    <section className="section" data-tour="projects"><SectionHeading title="Recent projects" copy={jobs.length ? "Your latest work, ready to continue." : "Your completed and in-progress work will appear here."}><button className="text-button" type="button" onClick={() => go("projects")}>See all</button></SectionHeading>
      {jobs.length ? <div className="project-grid">{jobs.slice(0, 4).map((job) => <ProjectCard key={job.video_id} item={job} onOpen={() => openVideo(job.video_id)} />)}</div> : <div className="getting-started"><div><h2>Your workspace is ready</h2><p>Choose a format, add the required presenter or visual inputs, then approve the production before rendering starts.</p></div><div className="step-list"><span className="step"><b>1</b>Create</span><span className="step"><b>2</b>Review</span><span className="step"><b>3</b>Export</span></div></div>}
    </section>
  </>;
}

function Studio({ preset, media, user, csrfToken, refresh, openVideo, showAlert, reportError }: { preset: StudioPreset; media: MediaItem[]; user: AuthUser; csrfToken: string; refresh: () => Promise<void>; openVideo: (id: string) => void; showAlert: (m: string) => void; reportError: (e: unknown) => void }) {
  const presenters = media.filter((item) => item.kind === "presenter");
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  function beginWork() {
    if (submitting.current) return false;
    submitting.current = true;
    setBusy(true);
    return true;
  }
  function endWork() {
    submitting.current = false;
    setBusy(false);
  }
  const [script, setScript] = useState(preset.script);
  const [visualDescription, setVisualDescription] = useState(preset.visualDescription);
  const [aspect, setAspect] = useState(preset.aspect);
  const [saved, setSaved] = useState<Project | null>(null);
  const [heygenAvatarId, setHeygenAvatarId] = useState("");
  const [heygenAvatarLabel, setHeygenAvatarLabel] = useState("");
  const [heygenVoiceId, setHeygenVoiceId] = useState("");
  const [higgsfieldReferenceImage, setHiggsfieldReferenceImage] = useState("");
  const [higgsfieldModel, setHiggsfieldModel] = useState("wan/v2.7/image-to-video");
  const [higgsfieldMotionPrompt, setHiggsfieldMotionPrompt] = useState("Natural presenter motion, realistic blinking, subtle head movement, natural hair movement, stable camera, and clean frames.");
  const [scenePlan, setScenePlan] = useState<Array<{ type: "PRESENTER" | "SPLIT" | "FULL_VISUAL"; visual_prompt: string }>>([]);
  const [catalog, setCatalog] = useState<HeyGenCatalog | null>(null);
  useEffect(() => {
    setScript(preset.script);
    setVisualDescription(preset.visualDescription);
    setAspect(preset.aspect);
    setSaved(null);
    setHiggsfieldReferenceImage("");
    setHiggsfieldModel("wan/v2.7/image-to-video");
    setHiggsfieldMotionPrompt("Natural presenter motion, realistic blinking, subtle head movement, natural hair movement, stable camera, and clean frames.");
    setScenePlan(preset.id === "story" ? [
      { type: "PRESENTER", visual_prompt: "Front-facing presenter introduces the hook with a warm, natural delivery." },
      { type: "FULL_VISUAL", visual_prompt: "A matching vertical lifestyle or product cutaway that illustrates the main point." },
      { type: "SPLIT", visual_prompt: "Presenter on one side with a supporting visual on the other side." },
      { type: "FULL_VISUAL", visual_prompt: "A close-up detail or screen-recording style visual that explains the next step." },
      { type: "FULL_VISUAL", visual_prompt: "A clean visual example with gentle motion and readable on-screen emphasis." },
      { type: "PRESENTER", visual_prompt: "Presenter returns for a concise conclusion and call to action." },
    ] : []);
  }, [preset]);
  useEffect(() => {
    void workspaceApi.heygenCatalog(csrfToken).then((loaded) => {
      setCatalog(loaded);
      setHeygenVoiceId((current) => current || loaded.default_voice_id || "");
    }).catch(() => setCatalog({ configured: false, voices: [], avatars: [] }));
  }, [csrfToken]);
  async function performRegister(avatarId = heygenAvatarId, label = heygenAvatarLabel) {
    const resolved = avatarId.trim();
    if (!resolved) {
      reportError(new Error("Enter the HeyGen avatar ID from the channel’s HeyGen account."));
      return null;
    }
    const uploaded = await workspaceApi.registerHeyGenAvatar(resolved, label.trim(), csrfToken);
    showAlert(`Registered HeyGen avatar ${uploaded.original_filename}`);
    setHeygenAvatarId("");
    setHeygenAvatarLabel("");
    await refresh();
    return uploaded;
  }
  async function registerHeyGenAvatar(avatarId = heygenAvatarId, label = heygenAvatarLabel) {
    if (!beginWork()) return null;
    try {
      return await performRegister(avatarId, label);
    } catch (error) { reportError(error); return null; } finally { endWork(); }
  }
  function projectFromForm(form: FormData): Project {
    const presenterId = preset.needsAvatar
      ? (preset.id === "story" ? higgsfieldReferenceImage.trim() : String(form.get("presenter_id") || heygenAvatarId).trim())
      : "";
    const voiceId = String(form.get("heygen_voice_id") || form.get("voice_id") || "provider_voice").trim();
    const now = new Date().toISOString();
    const dimensions = outputFor(aspect, Number(form.get("resolution")));
    const consent = [
      { subject_id: voiceId, permission_type: "voice", granted_by: user.email, granted_at: now, evidence_uri: `self-attested:${voiceId}` },
    ];
    if (presenterId) {
      consent.unshift({ subject_id: presenterId, permission_type: "avatar", granted_by: user.email, granted_at: now, evidence_uri: `self-attested:${presenterId}` });
    }
    return {
      project_id: saved?.project_id ?? `studio_${Date.now().toString(36)}`,
      schema_version: "1.0",
      presenter_provider: preset.id === "story" ? "authorized_higgsfield" : preset.needsAvatar ? "authorized_heygen" : undefined,
      scene_plan: preset.id === "story" ? scenePlan : undefined,
      channel_template: form.get("captions") === "none" ? "presenter_no_captions" : preset.channelTemplate,
      require_clean_export: form.get("require_clean_export") === "on",
      approval_state: "draft",
      output: { ...dimensions, fps: 30, aspect_ratio: aspect, video_codec: "h264", audio_codec: "aac" },
      scenes: [{
        scene_id: preset.visualFormat === "FULL_VISUAL" ? "visual" : "presenter",
        order: 1,
        visual_format: preset.visualFormat,
        narration_text: script,
        visual_description: preset.visualFormat === "PRESENTER" ? null : visualDescription,
        avatar_id: preset.needsAvatar ? presenterId : null,
        voice_id: voiceId,
        duration_seconds: null,
        layout_preset: preset.visualFormat === "FULL_VISUAL" ? "full_visual" : "presenter_centered",
        transition_out: "cut",
        visual_provider: "image",
        higgsfield_model: preset.id === "story" ? higgsfieldModel : undefined,
        higgsfield_motion_prompt: preset.id === "story" ? higgsfieldMotionPrompt : undefined,
      }],
      consent_records: consent,
    };
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!beginWork()) return;
    const form = new FormData(event.currentTarget);
    const intent = ((event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value ?? "render";
    try {
      if (intent === "render" && form.get("rights") !== "on") {
        reportError(new Error(`Confirm you have permission to use this ${preset.id === "story" ? "reference image and audio" : "avatar and voice"}.`));
        return;
      }
      if (preset.needsAvatar && preset.id !== "story" && heygenAvatarId.trim() && !presenters.some((item) => item.media_id === heygenAvatarId.trim())) {
        const registered = await performRegister();
        if (!registered) return;
      }
      const project = projectFromForm(form);
      if (preset.needsAvatar && !project.scenes[0]?.avatar_id) {
        reportError(new Error(`Add a ${preset.id === "story" ? "Higgsfield reference-image path" : "presenter avatar"} before approving the script.`));
        return;
      }
      const draft = await workspaceApi.saveProject(project, csrfToken);
      setSaved(draft);
      if (intent === "save") {
        showAlert(`Saved ${draft.project_id} as a draft`);
        await refresh();
        return;
      }
      const approved = await workspaceApi.approveProject(draft.project_id, csrfToken);
      const created = await workspaceApi.createVideo(approved, csrfToken);
      showAlert(`Queued ${created.video_id}`);
      await refresh();
      openVideo(created.video_id);
    } catch (error) { reportError(error); } finally { endWork(); }
  }
  const blocked = busy || (preset.needsAvatar && (preset.id === "story" ? !higgsfieldReferenceImage.trim() : !presenters.length && !heygenAvatarId.trim()));
  return <>
    <PageHeader eyebrow={preset.eyebrow} title={preset.title} copy={preset.copy} />
    <div className="studio-grid">
      <form className="panel studio-controls" key={preset.id} onSubmit={(event) => void submit(event)}>
        <h2>Video setup</h2>
        <div className="provider-summary">
          <strong>{preset.id === "story" ? "Higgsfield visual story" : preset.needsAvatar ? "HeyGen talking presenter" : "Aivatar visual composition"}</strong>
          <span>{preset.id === "story" ? "Presenter motion and visual direction are generated through Higgsfield." : preset.needsAvatar ? "HeyGen handles the presenter, voice, and lip synchronization." : "Aivatar assembles the narration, visuals, captions, and export locally."}</span>
        </div>
        <label className="field"><span>Script</span><textarea name="script" rows={8} required maxLength={12000} value={script} onChange={(event) => { setScript(event.target.value); setSaved(null); }} /></label>
        {preset.visualFormat !== "PRESENTER" && (
          <label className="field"><span>Visual direction</span><textarea rows={4} required maxLength={2000} value={visualDescription} onChange={(event) => { setVisualDescription(event.target.value); setSaved(null); }} placeholder="Describe the supporting shots, colors, pacing, and transitions." /></label>
        )}
        {preset.id === "story" && <section className="scene-plan-editor" aria-labelledby="scene-plan-title">
          <div className="scene-plan-heading"><div><h3 id="scene-plan-title">Scene plan</h3><p className="muted tiny">Aivatar follows these formats when it builds the final timeline.</p></div><span className="muted tiny">{scenePlan.length} scenes</span></div>
          {scenePlan.map((scene, index) => <div className="scene-plan-row" key={index}>
            <span className="scene-number">{index + 1}</span>
            <select aria-label={`Scene ${index + 1} format`} value={scene.type} onChange={(event) => setScenePlan((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, type: event.target.value as typeof scene.type } : item))} disabled={busy}>
              <option value="PRESENTER">Presenter</option><option value="SPLIT">Split</option><option value="FULL_VISUAL">Full visual</option>
            </select>
            <input aria-label={`Scene ${index + 1} visual direction`} value={scene.visual_prompt} onChange={(event) => setScenePlan((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, visual_prompt: event.target.value } : item))} disabled={busy} />
          </div>)}
        </section>}
        {preset.needsAvatar && (
          preset.id === "story" ? (
          <>
            <label className="field"><span>Presenter image</span><input name="reference_image_path" value={higgsfieldReferenceImage} onChange={(event) => setHiggsfieldReferenceImage(event.target.value)} placeholder="/path/to/presenter.png" autoComplete="off" disabled={busy} required /></label>
            <p className="muted tiny">Use a front-facing image you own or have permission to animate.</p>
            <label className="field"><span>Presenter motion</span><textarea name="higgsfield_motion_prompt" rows={3} value={higgsfieldMotionPrompt} onChange={(event) => setHiggsfieldMotionPrompt(event.target.value)} disabled={busy} /></label>
          </>
          ) : <>
            {catalog && !catalog.configured ? <p className="muted tiny">HeyGen is selected, but the API key is not configured yet. Export will wait until the key is added.</p> : null}
            {catalog?.avatars.length ? (
              <label className="field"><span>HeyGen account avatars</span><select value={heygenAvatarId} onChange={(event) => { const selected = catalog.avatars.find((item) => item.avatar_id === event.target.value); setHeygenAvatarId(event.target.value); setHeygenAvatarLabel(selected?.name ?? ""); }}><option value="">Choose a HeyGen avatar</option>{catalog.avatars.map((item) => <option value={item.avatar_id} key={item.avatar_id}>{item.name}</option>)}</select></label>
            ) : null}
            <label className="field"><span>HeyGen avatar ID</span><input value={heygenAvatarId} onChange={(event) => setHeygenAvatarId(event.target.value)} placeholder="Paste the HeyGen avatar ID" autoComplete="off" disabled={busy} /></label>
            <p className="muted tiny">Use the ID from the channel’s HeyGen account. A still image is not accepted.</p>
            <label className="field"><span>Avatar label</span><input value={heygenAvatarLabel} onChange={(event) => setHeygenAvatarLabel(event.target.value)} placeholder="Channel name (optional)" autoComplete="off" disabled={busy} /></label>
            <button className="btn secondary" type="button" disabled={busy} onClick={() => void registerHeyGenAvatar()}>{busy ? "Working…" : "Register HeyGen avatar"}</button>
            <label className="field"><span>Registered HeyGen avatar</span><select name="presenter_id" required={presenters.length > 0} defaultValue={presenters[0]?.media_id ?? ""}>{presenters.length ? presenters.map((item) => <option value={item.media_id} key={item.media_id}>{item.original_filename}</option>) : <option value="">Register a HeyGen avatar ID first</option>}</select></label>
          </>
        )}
        {preset.id !== "story" && catalog?.voices.length ? (
          <label className="field"><span>HeyGen voice</span><select name="heygen_voice_id" value={heygenVoiceId} onChange={(event) => setHeygenVoiceId(event.target.value)}><option value={catalog.default_voice_id || "provider_voice"}>Configured HeyGen voice</option>{catalog.voices.map((item) => <option value={item.voice_id} key={item.voice_id}>{item.name}{item.language ? ` · ${item.language}` : ""}</option>)}</select></label>
        ) : preset.id !== "story" ? (
          <label className="field"><span>HeyGen voice ID</span><input name="heygen_voice_id" value={heygenVoiceId} onChange={(event) => setHeygenVoiceId(event.target.value)} placeholder="Leave blank to use the configured HeyGen voice" autoComplete="off" disabled={busy} /></label>
        ) : null}
        <input type="hidden" name="voice_id" value={heygenVoiceId || "provider_voice"} />
        {preset.id === "story" ? <>
          <input type="hidden" name="aspect" value="16:9" />
          <input type="hidden" name="resolution" value="1080" />
          <input type="hidden" name="captions" value="burned" />
          <input type="hidden" name="require_clean_export" value="on" />
          <div className="export-summary" aria-label="YouTube-ready export settings">
            <div><strong>YouTube-ready export</strong><span>Optimized for direct upload</span></div>
            <p>1080p · 16:9 · 30 fps · MP4</p>
            <p>H.264 video · AAC audio · captions inside the safe area · clean export</p>
          </div>
        </> : <>
          <div className="control-row"><label className="field"><span>Aspect ratio</span><select name="aspect" value={aspect} onChange={(event) => setAspect(event.target.value as StudioPreset["aspect"])}><option>16:9</option><option>9:16</option><option>1:1</option><option>4:5</option></select></label><label className="field"><span>Resolution</span><select name="resolution" defaultValue={preset.resolution}><option value="720">720p</option><option value="1080">1080p</option></select></label></div>
          <label className="field"><span>Captions</span><select name="captions" defaultValue={preset.captions}><option value="burned">Burned-in captions</option><option value="none">None</option></select></label>
          <details className="advanced-settings"><summary>Advanced export settings</summary><label className="rights"><input name="require_clean_export" type="checkbox" defaultChecked /> Require a licensed clean export</label><p className="muted tiny">HeyGen exports the presenter through the official API. A licensed plan is required for a clean MP4.</p></details>
        </>}
        <label className="rights"><input name="rights" type="checkbox" /> I own or have permission to use the selected presenter image.</label>
        <div className="dialog-actions">
          {preset.id !== "story" && <button className="btn secondary" type="submit" name="intent" value="save" disabled={blocked}>{busy ? "Working…" : "Save draft"}</button>}
          <button className="btn primary" type="submit" name="intent" value="render" disabled={blocked}><Icon name="spark" />{busy ? "Working…" : "Approve and generate"}</button>
        </div>
        <p className="muted tiny">{preset.id === "story" ? "Aivatar sends the presenter image and narration to Higgsfield, then assembles the final 1080p story with captions." : "Studio asks for a HeyGen avatar ID, not a still. HeyGen exports the presenter after you approve the script."}</p>
      </form>
      <section className="panel preview-panel">
        <h2>Review before you render</h2>
        <p className="muted">{saved ? `Saved as ${saved.project_id} · ${saved.approval_state ?? "draft"}` : `${preset.visualFormat.replaceAll("_", " ")} · ${aspect}`}</p>
        <blockquote className="script-preview">{script || "Write a script to review it here."}</blockquote>
        {visualDescription && preset.visualFormat !== "PRESENTER" && <p className="muted tiny">{visualDescription}</p>}
      </section>
    </div>
  </>;
}

function Projects({ projects, jobs, openStudio, openVideo, csrfToken, refresh, showAlert, reportError }: { projects: Project[]; jobs: VideoJob[]; openStudio: (mode?: StudioMode) => void; openVideo: (id: string) => void; csrfToken: string; refresh: () => Promise<void>; showAlert: (m: string) => void; reportError: (e: unknown) => void }) {
  const [editing, setEditing] = useState<Project | null>(null);
  async function removeProject(projectId: string) {
    if (!window.confirm(`Delete saved script ${projectId}? Render history stays in Videos.`)) return;
    try {
      await workspaceApi.deleteProject(projectId, csrfToken);
      showAlert(`Deleted ${projectId}`);
      await refresh();
    } catch (error) {
      reportError(error);
    }
  }
  const groups = useMemo(() => {
    const map = new Map<string, { projects: Project[]; jobs: VideoJob[] }>();
    for (const project of projects) {
      const avatar = project.scenes.find((scene) => scene.avatar_id)?.avatar_id ?? "unassigned";
      const group = map.get(avatar) ?? { projects: [], jobs: [] };
      group.projects.push(project); map.set(avatar, group);
    }
    for (const job of jobs) {
      const project = projects.find((item) => item.project_id === job.project_id);
      const avatar = project?.scenes.find((scene) => scene.avatar_id)?.avatar_id ?? "unassigned";
      const group = map.get(avatar) ?? { projects: [], jobs: [] };
      group.jobs.push(job); map.set(avatar, group);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [jobs, projects]);
  return <>
    <PageHeader eyebrow="Projects" title="Saved projects by avatar" copy="Each avatar is a channel workspace with its own saved scripts, approval state, and delivery history."><button className="btn primary" type="button" onClick={() => openStudio()}><Icon name="plus" />New project</button></PageHeader>
    {groups.length ? groups.map(([avatar, group]) => <section className="section avatar-project-group" key={avatar}>
      <SectionHeading title={avatar === "unassigned" ? "Unassigned projects" : `Avatar: ${avatar}`} copy={avatar === "unassigned" ? "Projects without a presenter scene." : `${group.projects.length} saved project${group.projects.length === 1 ? "" : "s"} · ${group.jobs.length} render${group.jobs.length === 1 ? "" : "s"}`}><button className="text-button" type="button" onClick={() => openStudio()}>New video</button></SectionHeading>
      {group.jobs.length ? <div className="project-grid">{group.jobs.map((job) => <ProjectCard key={job.video_id} item={job} onOpen={() => openVideo(job.video_id)} />)}</div> : <section className="panel"><p className="muted">No renders for this avatar yet.</p></section>}
      <section className="panel"><h3>Saved project scripts</h3>{group.projects.length ? <div className="table-wrap"><table><thead><tr><th>Project</th><th>Template</th><th>Scenes</th><th>Approval</th><th>Output</th><th></th></tr></thead><tbody>{group.projects.map((project) => <tr key={project.project_id}><td><code>{project.project_id}</code></td><td>{project.channel_template}</td><td>{project.scenes.length}</td><td><span className={`badge ${project.approval_state === "approved" ? "ok" : "wait"}`}>{project.approval_state ?? "draft"}</span></td><td>{project.output.width}×{project.output.height} @ {project.output.fps}fps</td><td className="row-actions"><button className="text-button" type="button" onClick={() => setEditing(project)}>Edit script</button><button className="text-button" type="button" onClick={() => void removeProject(project.project_id)}>Delete</button></td></tr>)}</tbody></table></div> : <p className="muted">No saved scripts for this avatar yet.</p>}</section>
    </section>) : <div className="getting-started"><div><h2>Start your first avatar workspace</h2><p>Register the channel’s HeyGen avatar, then every project and render stays under that channel.</p></div><button className="btn primary" type="button" onClick={() => openStudio()}>Add HeyGen avatar</button></div>}
    {editing && <ScriptReviewDialog project={editing} csrfToken={csrfToken} onClose={() => setEditing(null)} onQueued={async (videoId) => { setEditing(null); openVideo(videoId); await refresh(); }} onSaved={async (project) => { setEditing(project); await refresh(); showAlert(`Saved ${project.project_id}`); }} reportError={reportError} />}
  </>;
}

function Assets({ media, csrfToken, refresh, openStudio, showAlert, reportError }: { media: MediaItem[]; csrfToken: string; refresh: () => Promise<void>; openStudio: (mode?: StudioMode) => void; showAlert: (m: string) => void; reportError: (e: unknown) => void }) {
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<"presenter" | "voice">("presenter");
  const fileInput = useRef<HTMLInputElement>(null);
  const [heygenAvatarId, setHeygenAvatarId] = useState("");
  const [heygenAvatarLabel, setHeygenAvatarLabel] = useState("");
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    try {
      const uploaded = await workspaceApi.uploadMedia(kind, file, csrfToken);
      showAlert(`Registered ${uploaded.original_filename}`);
      await refresh();
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  }
  async function registerHeyGenAvatar() {
    const avatarId = heygenAvatarId.trim();
    if (!avatarId) {
      reportError(new Error("Enter the HeyGen avatar ID from the channel’s HeyGen account."));
      return;
    }
    setBusy(true);
    try {
      const uploaded = await workspaceApi.registerHeyGenAvatar(avatarId, heygenAvatarLabel.trim(), csrfToken);
      showAlert(`Registered HeyGen avatar ${uploaded.original_filename}`);
      setHeygenAvatarId("");
      setHeygenAvatarLabel("");
      await refresh();
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  }
  async function remove(item: MediaItem) {
    if (!window.confirm(`Remove ${item.original_filename} from your library?`)) return;
    try {
      await workspaceApi.deleteMedia(item.media_id, csrfToken);
      showAlert(`Removed ${item.original_filename}`);
      await refresh();
    } catch (error) {
      reportError(error);
    }
  }
  return <>
    <PageHeader eyebrow="Assets" title="Your media library" copy="Register the channel’s HeyGen avatar ID. Voice samples are optional when HeyGen uses its native presenter voice.">
      <div className="header-actions">
        <select className="chip-select" value={kind} onChange={(event) => setKind(event.target.value as "presenter" | "voice")} aria-label="Upload type">
          <option value="presenter">HeyGen avatar</option>
          <option value="voice">Voice sample</option>
        </select>
        {kind === "voice" ? (
          <button className="btn primary" type="button" disabled={busy} onClick={() => fileInput.current?.click()}><Icon name="upload" />{busy ? "Uploading…" : "Upload"}</button>
        ) : null}
        <input ref={fileInput} type="file" hidden accept="audio/wav,audio/mpeg,audio/flac,.wav,.mp3,.flac,.m4a" onChange={(event) => void upload(event.target.files?.[0])} />
      </div>
    </PageHeader>
    {kind === "presenter" ? (
      <section className="panel">
        <h2>Register a HeyGen avatar</h2>
        <div className="settings-form">
          <label className="field"><span>HeyGen avatar ID</span><input value={heygenAvatarId} onChange={(event) => setHeygenAvatarId(event.target.value)} placeholder="From the HeyGen avatar library" autoComplete="off" disabled={busy} /></label>
          <label className="field"><span>Label</span><input value={heygenAvatarLabel} onChange={(event) => setHeygenAvatarLabel(event.target.value)} placeholder="Channel name (optional)" autoComplete="off" disabled={busy} /></label>
          <button className="btn primary" type="button" disabled={busy} onClick={() => void registerHeyGenAvatar()}>{busy ? "Working…" : "Register HeyGen avatar"}</button>
        </div>
      </section>
    ) : null}
    {media.length ? <div className="project-grid">{media.map((asset) => (
      <article className="project-card asset-card" key={asset.media_id}>
        <button type="button" className="asset-open" onClick={() => openStudio(asset.kind === "voice" ? "avatar" : "avatar")}>
          <MediaThumb item={asset} />
          <div className="project-title"><strong>{asset.original_filename}</strong></div>
          <small>Authorized {asset.kind === "presenter" ? presenterKind(asset) : asset.kind} · ready to use</small>
        </button>
        <button className="icon-btn asset-delete" type="button" aria-label={`Delete ${asset.original_filename}`} onClick={() => void remove(asset)}><Icon name="trash" /></button>
      </article>
    ))}</div> : <div className="project-empty"><span>Your library is empty. Register a HeyGen avatar ID to start.</span></div>}
  </>;
}

function Templates({ openStudio, showAlert }: { openStudio: (mode?: StudioMode) => void; showAlert: (m: string) => void }) {
  return <><PageHeader eyebrow="Templates" title="Start with a format" copy="Each template opens studio with aspect ratio, captions, and scene type already set." /><div className="project-grid">{TEMPLATES.map((template) => <TemplateCard key={template.title} template={template} onSelect={() => { showAlert(`${template.title} loaded in studio.`); openStudio(template.id); }} />)}</div></>;
}

function Tools({ openStudio }: { openStudio: (mode?: StudioMode) => void }) {
  return <><PageHeader eyebrow="AI tools" title="Choose a focused workflow" copy="Keep the creative decision first; advanced configuration stays optional." /><div className="create-grid">{WORKFLOWS.map((item) => <ToolCard key={item.id} title={item.eyebrow} copy={item.copy} icon={item.icon} featured={item.featured} onClick={() => openStudio(item.id)} />)}</div></>;
}

function Videos({ jobs, selectedVideoId, csrfToken, refresh, reportError, showAlert, openVideo, openStudio }: { jobs: VideoJob[]; selectedVideoId: string | null; csrfToken: string; refresh: () => Promise<void>; reportError: (e: unknown) => void; showAlert: (m: string) => void; openVideo: (id: string) => void; openStudio: (mode?: StudioMode) => void }) {
  const [filter, setFilter] = useState<"all" | "active" | "done" | "failed">("all");
  const [query, setQuery] = useState("");
  const visible = jobs.filter((job) => {
    const haystack = `${job.video_id} ${job.project_id} ${job.state}`.toLowerCase();
    if (query && !haystack.includes(query.toLowerCase())) return false;
    if (filter === "done") return job.state === "COMPLETED";
    if (filter === "failed") return ["FAILED", "CANCELLED"].includes(job.state);
    if (filter === "active") return !["COMPLETED", "FAILED", "CANCELLED"].includes(job.state);
    return true;
  });
  const selected = jobs.find((job) => job.video_id === selectedVideoId);
  const [previewUrl, setPreviewUrl] = useState("");
  const [storage, setStorage] = useState("");
  useEffect(() => {
    let url = "";
    if (!selected?.output_asset_id) {
      queueMicrotask(() => setPreviewUrl(""));
      return;
    }
    Promise.all([workspaceApi.asset(selected.output_asset_id, csrfToken), workspaceApi.assetContent(selected.output_asset_id, csrfToken)])
      .then(async ([metadata, response]) => {
        if (!response.ok) throw new Error(`Preview unavailable: ${response.status}`);
        setStorage(metadata.retained ? "Stored privately in Cloudflare R2 · secure owner-scoped download" : "Stored on this server · R2 retention is not enabled");
        url = URL.createObjectURL(await response.blob()); setPreviewUrl(url);
      }).catch(reportError);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [csrfToken, reportError, selected?.output_asset_id]);
  async function cancel() {
    if (!selected || !window.confirm(`Cancel job for ${selected.video_id}?`)) return;
    try { await workspaceApi.cancelVideo(selected.video_id, csrfToken); showAlert(`Cancelled ${selected.video_id}`); await refresh(); } catch (error) { reportError(error); }
  }
  async function retry() {
    if (!selected || !window.confirm(`Retry ${selected.video_id}? A new job will be queued from the approved script.`)) return;
    try {
      const created = await workspaceApi.retryVideo(selected.video_id, csrfToken);
      showAlert(`Queued retry ${created.video_id}`);
      await refresh();
      openVideo(created.video_id);
    } catch (error) {
      reportError(error);
    }
  }
  return <><PageHeader eyebrow="Production" title="Video jobs" copy="Filter the queue, review stage cost, and download completed MP4s to share with the team.">
    <div className="header-actions"><button className="btn primary" type="button" onClick={() => openStudio()}><Icon name="plus" />New render</button></div>
  </PageHeader>
  <section className="basalt-job-kpis" aria-label="Production queue summary">
    <div className="basalt-job-kpi"><span className="label">All jobs</span><strong>{jobs.length}</strong><span className="muted tiny">Across every project</span></div>
    <div className="basalt-job-kpi"><span className="label">In progress</span><strong>{jobs.filter((job) => !["COMPLETED", "FAILED", "CANCELLED"].includes(job.state)).length}</strong><span className="muted tiny">Rendering or queued</span></div>
    <div className="basalt-job-kpi"><span className="label">Ready</span><strong>{jobs.filter((job) => job.state === "COMPLETED").length}</strong><span className="muted tiny">Available to download</span></div>
    <div className="basalt-job-kpi is-alert"><span className="label">Needs attention</span><strong>{jobs.filter((job) => ["FAILED", "CANCELLED"].includes(job.state)).length}</strong><span className="muted tiny">Failed or cancelled</span></div>
  </section>
  <div className="filter-bar basalt-filter-bar">
    <BaseTabs value={filter} onChange={(value) => setFilter(value as typeof filter)} items={[["all", "All"], ["active", "In progress"], ["done", "Ready"], ["failed", "Needs attention"]].map(([value, label]) => ({ value, label }))} />
    <label className="filter-search"><Icon name="search" /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by project or video" /></label>
  </div>
  <section className="panel">{visible.length ? <div className="table-wrap"><table><thead><tr><th>Video</th><th>Project</th><th>Status</th><th>Est. cost</th><th>Updated</th></tr></thead><tbody>{visible.map((job) => <tr key={job.video_id} className={job.video_id === selectedVideoId ? "is-selected" : undefined} onClick={() => openVideo(job.video_id)}><td><code>{job.video_id}</code></td><td>{job.project_id}</td><td><span className={`badge ${badgeClass(job.state)}`}>{job.state.replaceAll("_", " ")}</span></td><td>{money(job.actual_cost_usd ?? job.estimated_cost_usd)}</td><td>{new Date(job.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div> : <div className="project-empty"><span>{jobs.length ? "No jobs match this filter." : "No production jobs yet. Approve a studio script to queue the first render."}</span>{!jobs.length && <button className="btn primary" type="button" onClick={() => openStudio()}>Open studio</button>}</div>}</section>
  {selected && <section className="panel"><h2>Production workspace</h2><p><strong>{selected.video_id}</strong> · project <code>{selected.project_id}</code></p><p>Status <span className={`badge ${badgeClass(selected.state)}`}>{selected.state}</span>{selected.watermark_status && <> · watermark <span className={`badge ${selected.watermark_status === "CLEAN_AUTHORIZED" ? "ok" : "wait"}`}>{selected.watermark_status}</span></>}{selected.error_message && <> · {selected.error_message}</>}</p><p className="muted">Estimated {money(selected.estimated_cost_usd)}{selected.actual_cost_usd != null ? ` · recorded ${money(selected.actual_cost_usd)}` : ""}{selected.cost_entries?.some((entry) => entry.note?.startsWith("heygen")) ? " · HeyGen Avatar IV" : selected.cost_entries?.some((entry) => entry.note === "local_proof_replay") ? " · packaged replay $0" : selected.cost_entries?.some((entry) => entry.note === "gpu_estimate" || entry.note === "wall_clock_gpu_rate") ? " · GPU $0.22/hr" : ""}</p>
    {!previewUrl && selected.state === "COMPLETED" && !selected.output_asset_id && <p className="muted">This job finished without a downloadable file. Retry it or start a new render.</p>}
    {!previewUrl && !["COMPLETED", "FAILED", "CANCELLED"].includes(selected.state) && <p className="muted">Preview appears here when the final MP4 is ready.</p>}
    <div className="header-actions"><button className="btn secondary" type="button" onClick={() => void cancel()} disabled={["COMPLETED", "FAILED", "CANCELLED"].includes(selected.state)}>Cancel job</button><button className="btn secondary" type="button" onClick={() => void retry()} disabled={!["FAILED", "CANCELLED"].includes(selected.state)}>Retry job</button></div>{previewUrl && <div className="video-result"><video src={previewUrl} controls playsInline aria-label="Generated video preview" /><div><a className="btn primary" download={`${selected.video_id}.mp4`} href={previewUrl}>Download MP4</a><p className="muted tiny">{storage}</p></div></div>}<h3>Stage timeline</h3><ul className="timeline">{STAGES.map((stage) => { const hit = selected.transitions.find((transition) => transition.to_state === stage); const current = selected.state === stage; return <li key={stage}><span className={`badge ${current ? badgeClass(stage) : hit ? "ok" : ""}`}>{stage}</span><span className="muted">{hit ? new Date(hit.at).toLocaleString() : current ? "Current" : "—"}</span></li>; })}</ul></section>}
  </>;
}

function Settings({
  data,
  user,
  csrfToken,
  showAlert,
  reportError,
  onSessionUpdated,
}: {
  data: WorkspaceData;
  user: AuthUser;
  csrfToken: string;
  showAlert: (message: string, kind?: "ok" | "error") => void;
  reportError: (error: unknown) => void;
  onSessionUpdated?: (session: Session) => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState<"profile" | "password" | "">("");
  useEffect(() => {
    setDisplayName(user.display_name);
  }, [user.display_name]);
  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy("profile");
    try {
      const session = await authApi.updateProfile(displayName, csrfToken);
      onSessionUpdated?.(session);
      showAlert("Display name updated");
    } catch (error) {
      reportError(error);
    } finally {
      setBusy("");
    }
  }
  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setBusy("password");
    try {
      const result = await authApi.changePassword(currentPassword, newPassword, csrfToken);
      setCurrentPassword("");
      setNewPassword("");
      showAlert(result.message);
    } catch (error) {
      reportError(error);
    } finally {
      setBusy("");
    }
  }
  return <>
    <PageHeader eyebrow="Workspace" title="Settings" copy="Manage your account, review render cost, and check production readiness." />
    <section className="panel">
      <h2>Account</h2>
      <form className="settings-form" onSubmit={(event) => void saveProfile(event)}>
        <label className="field"><span>Display name</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} minLength={1} maxLength={120} required /></label>
        <label className="field"><span>Email</span><input value={user.email} disabled /></label>
        <button className="btn secondary" type="submit" disabled={busy === "profile"}>{busy === "profile" ? "Saving…" : "Save profile"}</button>
      </form>
      <form className="settings-form" onSubmit={(event) => void savePassword(event)}>
        <label className="field"><span>Current password</span><input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" /></label>
        <label className="field"><span>New password</span><input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} required autoComplete="new-password" /></label>
        <button className="btn secondary" type="submit" disabled={busy === "password"}>{busy === "password" ? "Updating…" : "Update password"}</button>
      </form>
    </section>
    <section className="panel">
      <h2>Cost ledger</h2>
      <p className="muted tiny">{data.costs.billing_policy ?? "Presenter, voice, visual, and GPU costs are tracked per provider and render."}</p>
      <div className="grid">
        <div className="stat"><div className="label">Estimated</div><div className="value">{money(data.costs.estimated_usd)}</div></div>
        <div className="stat"><div className="label">Recorded</div><div className="value">{money(data.costs.actual_usd)}</div></div>
        <div className="stat"><div className="label">Presenter jobs</div><div className="value">{data.costs.heygen_job_count ?? data.costs.job_count}</div></div>
        <div className="stat"><div className="label">Active provider</div><div className="value">{data.avatarVideoProvider ?? "unknown"}</div></div>
      </div>
      {data.costs.projects.length ? <div className="table-wrap"><table><thead><tr><th>Project</th><th>Jobs</th><th>Estimated</th><th>Recorded</th></tr></thead><tbody>{data.costs.projects.map((item) => <tr key={item.project_id}><td><code>{item.project_id}</code></td><td>{item.job_count}</td><td>{money(item.estimated_usd)}</td><td>{money(item.actual_usd)}</td></tr>)}</tbody></table></div> : <p className="muted">No billed jobs yet. Costs will appear when a provider-backed render runs.</p>}
    </section>
    <section className="panel"><h2>Runtime status</h2><div className="grid"><div className="stat"><div className="label">API</div><div className="value">{data.health}</div></div><div className="stat"><div className="label">Runtime</div><div className="value">{data.ready}</div></div><div className="stat"><div className="label">Primary presenter</div><div className="value">{data.avatarVideoProvider ?? "unknown"}</div></div><div className="stat"><div className="label">Primary status</div><div className="value">{data.presenterProviderStatus ?? "unknown"}</div></div><div className="stat"><div className="label">Queued jobs</div><div className="value">{data.jobs.filter((job) => ["PENDING", "QUEUED"].includes(job.state)).length}</div></div></div></section>
    <section className="panel"><h2>Production notes</h2><p className="muted">Source watermark integrity, consent records, and clean-export validation are enforced before rendering resources are allocated. Apple sign-in stays visible but paused.</p><p className="muted tiny">Metrics endpoint: {data.metrics ? "connected" : "no samples yet"}</p></section>
  </>;
}

function ScriptReviewDialog({
  project,
  csrfToken,
  onClose,
  onQueued,
  onSaved,
  reportError,
}: {
  project: Project;
  csrfToken: string;
  onClose: () => void;
  onQueued: (videoId: string) => Promise<void>;
  onSaved: (project: Project) => Promise<void>;
  reportError: (error: unknown) => void;
}) {
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [scenes, setScenes] = useState(() => project.scenes.map((scene) => ({ ...scene })));
  const draft: Project = { ...project, scenes, approval_state: "draft" };
  async function save() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      const saved = await workspaceApi.replaceProject(draft, csrfToken);
      await onSaved(saved);
    } catch (error) { reportError(error); } finally { submitting.current = false; setBusy(false); }
  }
  async function approveAndRender() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      const saved = await workspaceApi.replaceProject(draft, csrfToken);
      const approved = await workspaceApi.approveProject(saved.project_id, csrfToken);
      const created = await workspaceApi.createVideo(approved, csrfToken);
      await onQueued(created.video_id);
    } catch (error) { reportError(error); } finally { submitting.current = false; setBusy(false); }
  }
  return (
    <dialog className="script-dialog" open aria-labelledby="script-title">
      <form onSubmit={(event) => { event.preventDefault(); void save(); }}>
        <button className="dialog-close icon-btn" type="button" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
        <p className="eyebrow">Script review</p>
        <h2 id="script-title">Edit and approve {project.project_id}</h2>
        <p className="muted">Saving a change returns the script to draft. Rendering requires a fresh approval.</p>
        <div className="script-scenes">
          {scenes.map((scene, index) => (
            <label className="field" key={scene.scene_id}>
              <span>{scene.scene_id} · {scene.visual_format}</span>
              <textarea
                rows={4}
                required
                maxLength={12000}
                value={scene.narration_text}
                onChange={(event) => setScenes((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, narration_text: event.target.value } : item))}
              />
            </label>
          ))}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn secondary" onClick={onClose}>Close</button>
          <button type="submit" className="btn secondary" disabled={busy}>{busy ? "Working…" : "Save draft"}</button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => void approveAndRender()}>{busy ? "Working…" : "Approve and generate"}</button>
        </div>
      </form>
    </dialog>
  );
}

