import type {
  AssetMetadata,
  AuthConfig,
  CostLedger,
  CreateVideoResponse,
  HeyGenCatalog,
  MediaItem,
  MessageResponse,
  Project,
  Session,
  VideoJob,
  WorkspaceData,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail)
        : typeof payload === "string"
          ? payload
          : "Something went wrong.";
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
  csrfToken = "",
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return parseResponse<T>(
    await fetch(path, { ...options, headers, credentials: "same-origin" }),
  );
}

export const authApi = {
  config: () => request<AuthConfig>("/v1/auth/config"),
  session: () => request<Session>("/v1/auth/session"),
  login: (email: string, password: string) =>
    request<Session>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (displayName: string, email: string, password: string) =>
    request<MessageResponse>("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, email, password }),
    }),
  forgotPassword: (email: string) =>
    request<MessageResponse>("/v1/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    request<Session>("/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),
  verifyEmail: (token: string) =>
    request<Session>("/v1/auth/verify-email", {
      method: "POST",
      body: JSON.stringify({ token }),
    }),
  logout: (csrfToken: string) =>
    request<void>("/v1/auth/logout", { method: "POST" }, csrfToken),
  updateProfile: (displayName: string, csrfToken: string) =>
    request<Session>(
      "/v1/auth/profile",
      { method: "PATCH", body: JSON.stringify({ display_name: displayName }) },
      csrfToken,
    ),
  changePassword: (currentPassword: string, newPassword: string, csrfToken: string) =>
    request<MessageResponse>(
      "/v1/auth/change-password",
      {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      },
      csrfToken,
    ),
};

export async function loadWorkspace(csrfToken: string): Promise<WorkspaceData> {
  const [health, ready, projects, jobs, metrics, media, costs] = await Promise.all([
    request<{
      status: string;
      avatar_video_provider?: string;
      heygen_configured?: boolean;
      heygen_engine?: string;
      heygen_rate_usd_per_minute?: number;
    }>("/health"),
    request<{ status: string }>("/ready").catch(() => ({ status: "not-ready" })),
    request<Project[]>("/v1/projects", {}, csrfToken),
    request<VideoJob[]>("/v1/videos", {}, csrfToken),
    request<string>("/metrics", {}, csrfToken),
    request<MediaItem[]>("/v1/media", {}, csrfToken),
    request<CostLedger>("/v1/costs", {}, csrfToken),
  ]);
  return {
    health: health.status,
    ready: ready.status,
    avatarVideoProvider: health.avatar_video_provider,
    heygenConfigured: health.heygen_configured,
    heygenEngine: health.heygen_engine,
    heygenRateUsdPerMinute: health.heygen_rate_usd_per_minute,
    projects,
    jobs,
    metrics,
    media,
    costs,
  };
}

export const workspaceApi = {
  saveProject: (project: Project, csrfToken: string) =>
    request<Project>(
      "/v1/projects",
      { method: "POST", body: JSON.stringify({ ...project, approval_state: "draft" }) },
      csrfToken,
    ),
  replaceProject: (project: Project, csrfToken: string) =>
    request<Project>(
      `/v1/projects/${encodeURIComponent(project.project_id)}`,
      { method: "PUT", body: JSON.stringify({ ...project, approval_state: "draft" }) },
      csrfToken,
    ),
  approveProject: (projectId: string, csrfToken: string) =>
    request<Project>(
      `/v1/projects/${encodeURIComponent(projectId)}/approve`,
      { method: "POST" },
      csrfToken,
    ),
  createVideo: (project: Project, csrfToken: string, key = crypto.randomUUID()) =>
    request<CreateVideoResponse>(
      "/v1/videos",
      {
        method: "POST",
        headers: { "Idempotency-Key": `studio-${key}` },
        body: JSON.stringify(project),
      },
      csrfToken,
    ),
  cancelVideo: (videoId: string, csrfToken: string) =>
    request<VideoJob>(
      `/v1/videos/${encodeURIComponent(videoId)}/cancel`,
      { method: "POST" },
      csrfToken,
    ),
  retryVideo: (videoId: string, csrfToken: string) =>
    request<CreateVideoResponse>(
      `/v1/videos/${encodeURIComponent(videoId)}/retry`,
      { method: "POST" },
      csrfToken,
    ),
  deleteProject: (projectId: string, csrfToken: string) =>
    request<void>(
      `/v1/projects/${encodeURIComponent(projectId)}`,
      { method: "DELETE" },
      csrfToken,
    ),
  asset: (assetId: string, csrfToken: string) =>
    request<AssetMetadata>(
      `/v1/assets/${encodeURIComponent(assetId)}`,
      {},
      csrfToken,
    ),
  assetContent: (assetId: string, csrfToken: string) =>
    fetch(`/v1/assets/${encodeURIComponent(assetId)}/content`, {
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    }),
  deleteMedia: (mediaId: string, csrfToken: string) =>
    request<void>(
      `/v1/media/${encodeURIComponent(mediaId)}`,
      { method: "DELETE" },
      csrfToken,
    ),
  mediaContent: (mediaId: string) => `/v1/media/${encodeURIComponent(mediaId)}/content`,
  heygenCatalog: (csrfToken: string) =>
    request<HeyGenCatalog>("/v1/heygen/catalog", {}, csrfToken),
  registerHeyGenAvatar: (avatarId: string, label: string, csrfToken: string) =>
    request<MediaItem>(
      "/v1/heygen-avatars",
      {
        method: "POST",
        headers: { "X-Media-Rights-Confirmed": "true" },
        body: JSON.stringify({ avatar_id: avatarId, label }),
      },
      csrfToken,
    ),
  uploadMedia: async (kind: string, file: File, csrfToken: string) => {
    const response = await fetch(`/v1/media/${encodeURIComponent(kind)}`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRF-Token": csrfToken,
        "X-Filename": file.name,
        "X-Media-Rights-Confirmed": "true",
        "Content-Type": file.type || "application/octet-stream",
      },
      body: file,
    });
    return parseResponse<MediaItem>(response);
  },
};
