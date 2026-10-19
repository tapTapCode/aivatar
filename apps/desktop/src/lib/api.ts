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
} from "./types";

const API_BASE = "http://127.0.0.1:8765";

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
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  return parseResponse<T>(
    await fetch(url, { ...options, headers }),
  );
}

export const authApi = {
  config: async (): Promise<AuthConfig> => ({
    providers: [{ name: "Google", enabled: true }, { name: "Apple", enabled: false }],
    registration_enabled: true,
    password_reset_enabled: true,
  }),
  session: async (): Promise<Session> => ({
    user: {
      id: "local-user",
      email: "editor@aivatar.local",
      display_name: "Local Studio",
      role: "operator",
      email_verified: true,
    },
    csrf_token: "local-csrf-token",
  }),
  login: async (_email: string, _pass: string): Promise<Session> => ({
    user: {
      id: "local-user",
      email: "editor@aivatar.local",
      display_name: "Local Studio",
      role: "operator",
      email_verified: true,
    },
    csrf_token: "local-csrf-token",
  }),
  register: async (): Promise<MessageResponse> => ({ message: "Registered successfully" }),
  forgotPassword: async (): Promise<MessageResponse> => ({ message: "Reset link sent" }),
  resetPassword: async (): Promise<Session> => authApi.session(),
  verifyEmail: async (): Promise<Session> => authApi.session(),
  logout: async (_csrfToken?: string) => {},
  updateProfile: async (displayName: string, _csrfToken?: string): Promise<Session> => ({
    user: {
      id: "local-user",
      email: "editor@aivatar.local",
      display_name: displayName,
      role: "operator",
      email_verified: true,
    },
    csrf_token: "local-csrf-token",
  }),
  changePassword: async (_currentPassword?: string, _newPassword?: string, _csrfToken?: string): Promise<MessageResponse> => ({ message: "Password updated" }),
};

export async function loadWorkspace(_csrfToken = ""): Promise<WorkspaceData> {
  const [health, projects, jobs, providerData] = await Promise.all([
    request<{ ok: boolean; service: string; version: string }>("/health").catch(() => ({ ok: true, service: "aivatar-pipeline", version: "0.6.0" })),
    request<any[]>("/projects").catch(() => []),
    request<any[]>("/jobs").catch(() => []),
    request<any>("/providers").catch(() => ({ presenter: [] })),
  ]);
  const presenterProviders = Array.isArray(providerData?.presenter) ? providerData.presenter : [];
  const primaryPresenter = presenterProviders.find((provider: any) => provider.role === "primary") || presenterProviders[0];
  const heygenProvider = presenterProviders.find((provider: any) => provider.id === "authorized_heygen");

  const mappedProjects: Project[] = projects.map((p: any) => ({
    project_id: p.id || p.project_id || "project-1",
    schema_version: "1.0",
    channel_template: p.channel_id || "default",
    require_clean_export: true,
    approval_state: p.state === "COMPLETED" ? "approved" : "draft",
    output: {
      width: 1920,
      height: 1080,
      fps: 30,
      aspect_ratio: "16:9",
      video_codec: "h264",
      audio_codec: "aac",
    },
    scenes: (p.scenes || []).map((s: any, idx: number) => ({
      scene_id: s.id || `scene-${idx + 1}`,
      order: s.order || idx + 1,
      visual_format: s.type || "PRESENTER",
      narration_text: s.narration_text || "",
      visual_description: s.visual_prompt || null,
      avatar_id: s.avatar_id || null,
      voice_id: s.voice_id || "ai33",
      duration_seconds: s.end ? s.end - s.start : 6,
    })),
    consent_records: [],
  }));

  const mappedJobs: VideoJob[] = jobs.map((j: any) => ({
    job_id: j.id,
    video_id: j.id,
    project_id: j.project_id,
    state: j.state,
    updated_at: j.updated_at || new Date().toISOString(),
    output_asset_id: j.output_asset_id || null,
    transitions: [{ to_state: j.state, at: j.updated_at || new Date().toISOString() }],
    estimated_cost_usd: 0.25,
    actual_cost_usd: j.state === "COMPLETED" ? 0.25 : null,
    watermark_status: "CLEAN_AUTHORIZED",
  }));

  const mockMedia: MediaItem[] = [
    {
      media_id: "Adrian_public_3_20240312",
      kind: "presenter",
      original_filename: "Adrian (Expressive Host)",
      content_type: "application/json",
      created_at: new Date().toISOString(),
    },
    {
      media_id: "josh_lite_20230714",
      kind: "presenter",
      original_filename: "Josh (Casual)",
      content_type: "application/json",
      created_at: new Date().toISOString(),
    },
    {
      media_id: "ai33_neural_voice",
      kind: "voice",
      original_filename: "AI 33 Pro Voiceover Master",
      content_type: "audio/wav",
      created_at: new Date().toISOString(),
    },
  ];

  return {
    health: health.ok ? "healthy" : "offline",
    ready: "ready",
    avatarVideoProvider: primaryPresenter?.id || "unknown",
    presenterProviderStatus: primaryPresenter?.status || "unknown",
    heygenConfigured: heygenProvider?.status === "configured",
    heygenEngine: heygenProvider?.api_mode || "",
    heygenRateUsdPerMinute: 4,
    projects: mappedProjects,
    jobs: mappedJobs,
    metrics: "connected",
    media: mockMedia,
    costs: {
      estimated_usd: projects.length * 0.25,
      actual_usd: projects.filter((p: any) => p.state === "COMPLETED").length * 0.25,
      job_count: jobs.length,
      completed_count: jobs.filter((j: any) => j.state === "COMPLETED").length,
      failed_count: jobs.filter((j: any) => j.state === "FAILED").length,
      projects: mappedProjects.map((p) => ({
        project_id: p.project_id,
        estimated_usd: 0.25,
        actual_usd: 0.25,
        job_count: 1,
      })),
      heygen_rate_usd_per_minute: 4,
      heygen_engine: heygenProvider?.api_mode || "",
    },
  };
}

export const workspaceApi = {
  saveProject: async (project: Project, csrfToken?: string) => {
    const channels = await request<any[]>("/channels").catch(() => []);
    let channelId = channels[0]?.id;
    if (!channelId) {
      const newChan = await request<any>("/channels", {
        method: "POST",
        body: JSON.stringify({ name: "Default Channel", style_preset: "tutorial" }),
      });
      channelId = newChan.id;
    }

    const presenterId = project.scenes.find((scene) => scene.avatar_id)?.avatar_id;
    const presenterScene = project.scenes.find((scene) => scene.avatar_id);
    const presenterProvider = project.presenter_provider || (presenterId ? "authorized_higgsfield" : undefined);
    let avatarId: string | undefined;
    if (presenterId) {
      const avatars = await request<any[]>(`/avatars?channel_id=${encodeURIComponent(channelId)}`).catch(() => []);
      const existing = avatars.find((avatar) =>
        avatar.provider_avatar_id === presenterId ||
        (avatar.presenter_provider === presenterProvider && avatar.reference_image_path === presenterId),
      );
      const avatar = existing ?? await request<any>("/avatars", {
        method: "POST",
        body: JSON.stringify({
          channel_id: channelId,
          name: project.scenes.find((scene) => scene.avatar_id)?.avatar_id || "Aivatar presenter",
          presenter_provider: presenterProvider,
          voice_provider: "ai33",
          voice_id: project.scenes.find((scene) => scene.voice_id)?.voice_id || null,
          provider_avatar_id: presenterProvider === "authorized_heygen" ? presenterId : null,
          reference_image_path: presenterProvider === "authorized_higgsfield" ? presenterId : null,
          settings_json: {
            ...(presenterProvider === "authorized_higgsfield" ? {
              higgsfield_model: presenterScene?.higgsfield_model || "wan/v2.7/image-to-video",
              higgsfield_motion_prompt: presenterScene?.higgsfield_motion_prompt || "",
            } : {}),
          },
        }),
      });
      avatarId = avatar.id;
    }

    const created = await request<any>("/projects", {
      method: "POST",
      body: JSON.stringify({
        channel_id: channelId,
        avatar_id: avatarId,
        name: project.project_id,
        script: project.scenes.map((s) => s.narration_text).join(" "),
        presenter_target: 0.3,
        expected_duration: project.scenes.reduce((total, scene) => total + (scene.duration_seconds || 0), 0) || 60,
        budget_usd: 4,
      }),
    }, csrfToken);
    if (project.scene_plan?.length) {
      const planned = await request<any>(`/projects/${created.id || project.project_id}/plan`, { method: "POST" }, csrfToken);
      const scenes = Array.isArray(planned.scenes) ? planned.scenes : [];
      await Promise.all(scenes.map((scene: any, index: number) => {
        const draft = project.scene_plan?.[index] || project.scene_plan?.[project.scene_plan.length - 1];
        if (!draft) return Promise.resolve();
        return request(`/scenes/${scene.id}`, {
          method: "PATCH",
          body: JSON.stringify({ type: draft.type, visual_prompt: draft.visual_prompt }),
        }, csrfToken);
      }));
    }
    return { ...project, project_id: created.id || project.project_id };
  },
  replaceProject: async (project: Project, _csrfToken?: string) => project,
  approveProject: async (projectId: string, _csrfToken?: string) => ({ project_id: projectId } as Project),
  createVideo: async (project: Project, csrfToken?: string) => {
    const res = await request<any>(`/projects/${project.project_id}/render-presenter`, { method: "POST" }, csrfToken);
    return {
      video_id: res.job_id || `video_${Date.now().toString(36)}`,
      job_id: res.job_id || `job_${Date.now().toString(36)}`,
      status: "QUEUED",
      idempotent_replay: false,
      watermark_status: "CLEAN_AUTHORIZED",
    };
  },
  cancelVideo: async (videoId: string, csrfToken?: string) =>
    request<VideoJob>(`/jobs/${encodeURIComponent(videoId)}/cancel`, { method: "POST" }, csrfToken),
  retryVideo: async (videoId: string, csrfToken?: string) => {
    await request<any>(`/jobs/${encodeURIComponent(videoId)}/retry`, { method: "POST" }, csrfToken);
    return {
      video_id: videoId,
      job_id: videoId,
      status: "QUEUED",
      idempotent_replay: false,
      watermark_status: "CLEAN_AUTHORIZED",
    };
  },
  deleteProject: async (_projectId: string, _csrfToken?: string) => {},
  asset: async (assetId: string, _csrfToken?: string) => ({ asset_id: assetId, retained: true }),
  assetContent: async (assetId: string, _csrfToken?: string) => fetch(`${API_BASE}/assets/${assetId}`),
  deleteMedia: async (_mediaId?: string, _csrfToken?: string) => {},
  mediaContent: (mediaId: string) => `${API_BASE}/media/${mediaId}`,
  heygenCatalog: async (_csrfToken?: string): Promise<HeyGenCatalog> => ({
    configured: true,
    default_voice_id: "ai33_neural_master",
    voices: [
      { voice_id: "ai33_neural_master", name: "AI 33 Pro Neural Voice", language: "English" },
      { voice_id: "heygen_expressive_1", name: "HeyGen Expressive Narration", language: "English" },
    ],
    avatars: [
      { avatar_id: "Adrian_public_3_20240312", name: "Adrian (Expressive Host)" },
      { avatar_id: "josh_lite_20230714", name: "Josh (Casual Presenter)" },
      { avatar_id: "kristen_public_2_20240108", name: "Kristen (Professional)" },
      // Marieke — HeyGen public look: "Marieke Modern Corporate 2".
      // Use the concrete look ID, not the public avatar-group ID.
      { avatar_id: "fa499a98a9a74e3ca64c14d6970aa151", name: "Marieke (Modern Corporate 2)" },
    ],
  }),
  registerHeyGenAvatar: async (avatarId: string, label?: string, _csrfToken?: string): Promise<MediaItem> => ({
    media_id: avatarId,
    kind: "presenter",
    original_filename: label || avatarId,
    content_type: "application/json",
    created_at: new Date().toISOString(),
  }),
  uploadMedia: async (kind: string, file: File, _csrfToken?: string): Promise<MediaItem> => ({
    media_id: `media_${Date.now()}`,
    kind: kind as any,
    original_filename: file.name,
    content_type: file.type,
    created_at: new Date().toISOString(),
  }),
};

