/* eslint-disable @next/next/no-img-element */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/Dashboard";
import { authApi, loadWorkspace, workspaceApi } from "@/lib/api";
import type { Project } from "@/lib/types";

vi.mock("next/image", () => ({
  default: ({
    priority,
    ...props
  }: React.ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean }) => {
    void priority;
    return <img {...props} alt={props.alt ?? ""} />;
  },
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    loadWorkspace: vi.fn(),
    authApi: { ...actual.authApi, logout: vi.fn() },
    workspaceApi: {
      ...actual.workspaceApi,
      saveProject: vi.fn(),
      replaceProject: vi.fn(),
      approveProject: vi.fn(),
      createVideo: vi.fn(),
      uploadMedia: vi.fn(),
      registerHeyGenAvatar: vi.fn(),
      heygenCatalog: vi.fn().mockResolvedValue({
        configured: true,
        default_voice_id: "voice-1",
        voices: [],
        avatars: [],
      }),
      deleteMedia: vi.fn(),
    },
  };
});

const user = {
  id: "user-1",
  email: "client@example.com",
  display_name: "Client User",
  role: "member",
  email_verified: true,
};

describe("Dashboard", () => {
  beforeEach(() => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      projects: [],
      jobs: [],
      metrics: "# metrics",
      media: [
        {
          media_id: "presenter-1",
          kind: "presenter",
          original_filename: "channel-avatar",
          content_type: "application/json",
        },
      ],
      costs: {
        estimated_usd: 0,
        actual_usd: 0,
        job_count: 0,
        completed_count: 0,
        failed_count: 0,
        projects: [],
      },
    });
  });

  it("opens script review from a saved project", async () => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      projects: [
        {
          project_id: "demo_script",
          schema_version: "1.0",
          channel_template: "default",
          approval_state: "draft",
          output: { width: 640, height: 360, fps: 30, aspect_ratio: "16:9", video_codec: "h264", audio_codec: "aac" },
          scenes: [
            {
              scene_id: "presenter",
              order: 1,
              visual_format: "PRESENTER",
              narration_text: "Draft narration for review.",
              avatar_id: "presenter-1",
              voice_id: "provider_voice",
            },
          ],
          consent_records: [],
        },
      ],
      jobs: [],
      metrics: "# metrics",
      media: [],
      costs: {
        estimated_usd: 0,
        actual_usd: 0,
        job_count: 0,
        completed_count: 0,
        failed_count: 0,
        projects: [],
      },
    });
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Projects/ }));
    await userEvent.click(screen.getByRole("button", { name: "Edit script" }));
    expect(screen.getByRole("heading", { name: /Edit and approve demo_script/ })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Draft narration for review.")).toBeInTheDocument();
  });

  it("loads the workspace, navigates, and logs out with CSRF", async () => {
    const onSignedOut = vi.fn();
    vi.mocked(authApi.logout).mockResolvedValue();
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={onSignedOut} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Projects/ }));
    expect(screen.getByRole("heading", { name: "Saved projects by avatar" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Sign out/ }));
    await waitFor(() => expect(authApi.logout).toHaveBeenCalledWith("csrf-1"));
    expect(onSignedOut).toHaveBeenCalled();
  });

  it("saves, approves, and submits the studio payload", async () => {
    let latest: Project | null = null;
    vi.mocked(workspaceApi.saveProject).mockImplementation(async (project) => {
      latest = project;
      return { ...project, approval_state: "draft" };
    });
    vi.mocked(workspaceApi.approveProject).mockImplementation(async (projectId) => ({
      ...(latest as Project),
      project_id: projectId,
      approval_state: "approved",
    }));
    vi.mocked(workspaceApi.createVideo).mockResolvedValue({
      video_id: "vid-1",
      job_id: "job-1",
      status: "QUEUED",
      idempotent_replay: false,
      watermark_status: "PRESERVED",
    });
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getAllByRole("button", { name: /^Create$/ })[0]);
    expect(screen.getByText("HeyGen avatar ID")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Paste the HeyGen avatar ID")).toBeInTheDocument();
    await userEvent.click(screen.getByText(/I own or have permission/));
    await userEvent.click(screen.getByRole("button", { name: "Approve and generate" }));
    await waitFor(() => expect(workspaceApi.createVideo).toHaveBeenCalled());
    expect(workspaceApi.saveProject).toHaveBeenCalled();
    expect(workspaceApi.approveProject).toHaveBeenCalled();
    const project = vi.mocked(workspaceApi.createVideo).mock.calls[0][0];
    expect(project.scenes[0].avatar_id).toBe("presenter-1");
    expect(project.consent_records).toHaveLength(2);
    expect(project.approval_state).toBe("approved");
  });

  it("opens a social studio preset and shows job notifications", async () => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      projects: [],
      jobs: [
        {
          job_id: "job-9",
          video_id: "vid-ready",
          project_id: "social_cut",
          state: "COMPLETED",
          updated_at: new Date().toISOString(),
          transitions: [],
          estimated_cost_usd: 0.22,
        },
      ],
      metrics: "# metrics",
      media: [
        {
          media_id: "presenter-1",
          kind: "presenter",
          original_filename: "channel-avatar",
          content_type: "application/json",
        },
      ],
      costs: {
        estimated_usd: 0.22,
        actual_usd: 0,
        job_count: 1,
        completed_count: 1,
        failed_count: 0,
        projects: [],
      },
    });
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Social post/ }));
    expect(screen.getByRole("heading", { name: "Make a vertical social cut" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("9:16")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /unread notifications/ }));
    expect(screen.getByText("Video is ready")).toBeInTheDocument();
    expect(screen.getByText(/social_cut/)).toBeInTheDocument();
  });

  it("asks Studio for a HeyGen avatar ID instead of a MuseTalk still", async () => {
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getAllByRole("button", { name: /^Create$/ })[0]);
    expect(screen.getByRole("heading", { name: "Make an avatar video" })).toBeInTheDocument();
    expect(screen.getByText("HeyGen avatar ID")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Paste the HeyGen avatar ID")).toBeInTheDocument();
    expect(screen.getByText(/Studio asks for a HeyGen avatar ID, not a still/)).toBeInTheDocument();
    expect(screen.getByText(/A still image is not accepted/)).toBeInTheDocument();
    expect(screen.queryByText(/MuseTalk/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Add avatar")).not.toBeInTheDocument();
    expect(document.querySelectorAll('input[type="file"]')).toHaveLength(0);
    expect(document.querySelector('input[accept*="image"]')).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /Assets/ }));
    expect(screen.getByRole("heading", { name: "Register a HeyGen avatar" })).toBeInTheDocument();
    expect(screen.getByText("HeyGen avatar ID")).toBeInTheDocument();
    expect(screen.getByText(/Authorized HeyGen avatar/)).toBeInTheDocument();
    expect(screen.queryByText(/MuseTalk/i)).not.toBeInTheDocument();
    const assetFiles = [...document.querySelectorAll<HTMLInputElement>('input[type="file"]')];
    expect(assetFiles.every((input) => !/image/i.test(input.accept))).toBe(true);
  });

  it("covers the HeyGen default path from catalog ID to approve", async () => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      avatarVideoProvider: "heygen_api",
      heygenConfigured: true,
      projects: [],
      jobs: [],
      metrics: "# metrics",
      media: [],
      costs: {
        estimated_usd: 0,
        actual_usd: 0,
        job_count: 0,
        completed_count: 0,
        failed_count: 0,
        projects: [],
        billing_policy: "HeyGen Avatar IV is billed at the configured per-minute rate.",
        heygen_engine: "avatar_iv",
        heygen_rate_usd_per_minute: 4,
      },
    });
    vi.mocked(workspaceApi.heygenCatalog).mockResolvedValue({
      configured: true,
      default_voice_id: "voice-en",
      voices: [{ voice_id: "voice-en", name: "English Voice", language: "English" }],
      avatars: [{ avatar_id: "Angela-inblack-20220820", name: "Channel A" }],
    });
    vi.mocked(workspaceApi.registerHeyGenAvatar).mockReset();
    vi.mocked(workspaceApi.saveProject).mockReset();
    vi.mocked(workspaceApi.approveProject).mockReset();
    vi.mocked(workspaceApi.createVideo).mockReset();
    vi.mocked(workspaceApi.uploadMedia).mockReset();
    vi.mocked(workspaceApi.registerHeyGenAvatar).mockResolvedValue({
      media_id: "Angela-inblack-20220820",
      kind: "presenter",
      original_filename: "Channel A",
      content_type: "application/json",
    });
    let latest: Project | null = null;
    vi.mocked(workspaceApi.saveProject).mockImplementation(async (project) => {
      latest = project;
      return { ...project, approval_state: "draft" };
    });
    vi.mocked(workspaceApi.approveProject).mockImplementation(async (projectId) => ({
      ...(latest as Project),
      project_id: projectId,
      approval_state: "approved",
    }));
    vi.mocked(workspaceApi.createVideo).mockResolvedValue({
      video_id: "vid-heygen",
      job_id: "job-heygen",
      status: "QUEUED",
      idempotent_replay: false,
      watermark_status: "CLEAN_AUTHORIZED",
    });

    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    expect(screen.getByText(/Add the HeyGen avatar ID/)).toBeInTheDocument();
    expect(screen.queryByText(/MuseTalk/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: /^Create$/ })[0]);
    expect(screen.getByRole("heading", { name: "Make an avatar video" })).toBeInTheDocument();
    expect(screen.getByText("HeyGen avatar ID")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("HeyGen account avatars")).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("HeyGen account avatars"), "Angela-inblack-20220820");
    expect(screen.getByPlaceholderText("Paste the HeyGen avatar ID")).toHaveValue("Angela-inblack-20220820");
    expect(document.querySelectorAll('input[type="file"]')).toHaveLength(0);

    await userEvent.click(screen.getByText(/I own or have permission/));
    await userEvent.click(screen.getByRole("button", { name: "Approve and generate" }));
    await waitFor(() => expect(workspaceApi.registerHeyGenAvatar).toHaveBeenCalledWith(
      "Angela-inblack-20220820",
      "Channel A",
      "csrf-1",
    ));
    await waitFor(() => expect(workspaceApi.createVideo).toHaveBeenCalled());
    expect(workspaceApi.uploadMedia).not.toHaveBeenCalled();
    const project = vi.mocked(workspaceApi.createVideo).mock.calls.at(-1)?.[0];
    expect(project).toBeDefined();
    expect(project?.scenes[0].avatar_id).toBe("Angela-inblack-20220820");
    expect(project?.scenes[0].voice_id).toBe("voice-en");
    expect(project?.approval_state).toBe("approved");
  });

  it("does not enqueue two HeyGen jobs on a double generate click", async () => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      avatarVideoProvider: "heygen_api",
      heygenConfigured: true,
      projects: [],
      jobs: [],
      metrics: "# metrics",
      media: [
        {
          media_id: "Angela-inblack-20220820",
          kind: "presenter",
          original_filename: "Channel A",
          content_type: "application/json",
        },
      ],
      costs: {
        estimated_usd: 0,
        actual_usd: 0,
        job_count: 0,
        completed_count: 0,
        failed_count: 0,
        projects: [],
      },
    });
    let resolveCreate: ((value: { video_id: string; job_id: string; status: string; idempotent_replay: boolean; watermark_status: string }) => void) | undefined;
    vi.mocked(workspaceApi.saveProject).mockReset();
    vi.mocked(workspaceApi.approveProject).mockReset();
    vi.mocked(workspaceApi.createVideo).mockReset();
    vi.mocked(workspaceApi.saveProject).mockImplementation(async (project) => ({
      ...project,
      approval_state: "draft",
    }));
    vi.mocked(workspaceApi.approveProject).mockImplementation(async (projectId) => ({
      project_id: projectId,
      schema_version: "1.0",
      channel_template: "presenter_no_captions",
      require_clean_export: true,
      approval_state: "approved",
      output: { width: 1920, height: 1080, fps: 30, aspect_ratio: "16:9", video_codec: "h264", audio_codec: "aac" },
      scenes: [],
      consent_records: [],
    }));
    vi.mocked(workspaceApi.createVideo).mockImplementation(
      () => new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    );

    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getAllByRole("button", { name: /^Create$/ })[0]);
    await userEvent.click(screen.getByText(/I own or have permission/));
    const generate = screen.getByRole("button", { name: "Approve and generate" });
    generate.click();
    generate.click();
    await waitFor(() => expect(workspaceApi.saveProject).toHaveBeenCalledTimes(1));
    expect(workspaceApi.approveProject).toHaveBeenCalledTimes(1);
    expect(workspaceApi.createVideo).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(resolveCreate).toBeDefined());
    resolveCreate?.({
      video_id: "vid-once",
      job_id: "job-once",
      status: "QUEUED",
      idempotent_replay: false,
      watermark_status: "CLEAN_AUTHORIZED",
    });
    await waitFor(() => expect(workspaceApi.createVideo).toHaveBeenCalledTimes(1));
  });

  it("shows the HeyGen cost policy", async () => {
    vi.mocked(loadWorkspace).mockResolvedValue({
      health: "ok",
      ready: "ready",
      avatarVideoProvider: "heygen_api",
      heygenConfigured: true,
      projects: [],
      jobs: [],
      metrics: "# metrics",
      media: [],
      costs: {
        estimated_usd: 0,
        actual_usd: 0,
        job_count: 1,
        completed_count: 1,
        failed_count: 0,
        projects: [],
        billing_policy: "HeyGen Avatar IV is billed at the configured per-minute rate.",
        heygen_engine: "avatar_iv",
        heygen_rate_usd_per_minute: 4,
        heygen_job_count: 1,
        gpu_hourly_rate_usd: 0.22,
      },
    });
    render(<Dashboard user={user} csrfToken="csrf-1" onSignedOut={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("API ok · runtime ready")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Settings/ }));
    expect(screen.getByRole("heading", { name: "Cost ledger" })).toBeInTheDocument();
    expect(screen.getByText("HeyGen Avatar IV is billed at the configured per-minute rate.")).toBeInTheDocument();
    expect(screen.getByText("Avatar IV rate")).toBeInTheDocument();
    expect(screen.getByText("$4.00/min")).toBeInTheDocument();
    expect(screen.getByText("HeyGen jobs")).toBeInTheDocument();
    expect(screen.getByText("HeyGen Avatar IV")).toBeInTheDocument();
  });
});
