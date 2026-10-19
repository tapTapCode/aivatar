export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  email_verified: boolean;
};

export type Session = { user: AuthUser; csrf_token: string };
export type Provider = { name: "Google" | "Apple"; enabled: boolean };
export type AuthConfig = {
  providers: Provider[];
  registration_enabled: boolean;
  password_reset_enabled: boolean;
};
export type MessageResponse = { message: string; debug_url?: string | null };

export type MediaKind = "presenter" | "voice" | "background";

export type MediaItem = {
  media_id: string;
  kind: MediaKind;
  original_filename: string;
  content_type?: string;
  created_at?: string;
};

export type Transition = { from_state?: string; to_state: string; at: string };
export type VideoJob = {
  job_id: string;
  video_id: string;
  project_id: string;
  state: string;
  updated_at: string;
  transitions: Transition[];
  output_asset_id?: string | null;
  provider_ref?: string | null;
  error_message?: string | null;
  watermark_status?: string | null;
  cancellation_requested?: boolean;
  estimated_cost_usd?: number;
  actual_cost_usd?: number | null;
  cost_entries?: Array<{ stage: string; amount_usd: number; note?: string }>;
};

export type Scene = {
  scene_id: string;
  order: number;
  visual_format: string;
  narration_text: string;
  visual_description?: string | null;
  avatar_id?: string | null;
  voice_id?: string | null;
  duration_seconds?: number | null;
  layout_preset?: string;
  transition_out?: string;
  visual_provider?: string;
  higgsfield_model?: string;
  higgsfield_motion_prompt?: string;
};

export type ApprovalState = "draft" | "approved";

export type Project = {
  project_id: string;
  schema_version: string;
  presenter_provider?: "authorized_higgsfield" | "authorized_heygen" | "musetalk_fallback" | "manual_presenter_import";
  scene_plan?: Array<{ type: "PRESENTER" | "SPLIT" | "FULL_VISUAL"; visual_prompt: string }>;
  channel_template: string;
  require_clean_export?: boolean;
  approval_state?: ApprovalState;
  output: {
    width: number;
    height: number;
    fps: number;
    aspect_ratio: string;
    video_codec: string;
    audio_codec: string;
  };
  scenes: Scene[];
  consent_records: Array<Record<string, unknown>>;
};

export type AssetMetadata = {
  asset_id: string;
  retained: boolean;
  mime_type?: string;
};

export type CreateVideoResponse = {
  video_id: string;
  job_id: string;
  status: string;
  idempotent_replay: boolean;
  watermark_status: string;
};

export type ProjectCostSummary = {
  project_id: string;
  estimated_usd: number;
  actual_usd: number;
  job_count: number;
};

export type CostLedger = {
  estimated_usd: number;
  actual_usd: number;
  job_count: number;
  completed_count: number;
  failed_count: number;
  projects: ProjectCostSummary[];
  gpu_hourly_rate_usd?: number;
  heygen_rate_usd_per_minute?: number;
  heygen_engine?: string;
  billing_policy?: string;
  proof_replay_job_count?: number;
  gpu_job_count?: number;
  heygen_job_count?: number;
  heygen_estimated_usd?: number;
  heygen_actual_usd?: number;
  proof_replay_usd?: number;
  gpu_estimated_usd?: number;
  gpu_actual_usd?: number;
};

export type HeyGenVoiceOption = { voice_id: string; name: string; language?: string };
export type HeyGenAvatarOption = { avatar_id: string; name: string };
export type HeyGenCatalog = {
  configured: boolean;
  default_voice_id?: string;
  voices: HeyGenVoiceOption[];
  avatars: HeyGenAvatarOption[];
};

export type WorkspaceData = {
  health: string;
  ready: string;
  avatarVideoProvider?: string;
  presenterProviderStatus?: string;
  heygenConfigured?: boolean;
  heygenEngine?: string;
  heygenRateUsdPerMinute?: number;
  projects: Project[];
  jobs: VideoJob[];
  metrics: string;
  media: MediaItem[];
  costs: CostLedger;
};
