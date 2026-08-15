import { describe, expect, it } from "vitest";
import { STUDIO_PRESETS } from "@/lib/studio";

describe("HeyGen default studio presets", () => {
  it("asks presenter workflows for a HeyGen avatar ID", () => {
    for (const id of ["avatar", "story", "social"] as const) {
      expect(STUDIO_PRESETS[id].needsAvatar).toBe(true);
      expect(STUDIO_PRESETS[id].copy).toMatch(/HeyGen avatar ID/);
    }
    expect(STUDIO_PRESETS.image.needsAvatar).toBe(false);
    expect(STUDIO_PRESETS.presentation.needsAvatar).toBe(false);
    expect(STUDIO_PRESETS.avatar.captions).toBe("none");
  });
});
