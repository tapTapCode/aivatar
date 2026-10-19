export type StudioMode =
  | "avatar"
  | "story"
  | "image"
  | "presentation"
  | "social";

export type StudioPreset = {
  id: StudioMode;
  title: string;
  eyebrow: string;
  copy: string;
  icon: "avatar" | "video" | "image" | "slides" | "spark";
  featured?: boolean;
  aspect: "16:9" | "9:16" | "1:1" | "4:5";
  resolution: "720" | "1080";
  captions: "burned" | "none";
  visualFormat: "PRESENTER" | "SPLIT" | "FULL_VISUAL";
  channelTemplate: string;
  script: string;
  visualDescription: string;
  needsAvatar: boolean;
};

export const STUDIO_PRESETS: Record<StudioMode, StudioPreset> = {
  avatar: {
    id: "avatar",
    title: "Make an avatar video",
    eyebrow: "Presenter",
    copy: "Choose a HeyGen presenter, write the script, and export a polished talking-avatar video.",
    icon: "avatar",
    featured: true,
    aspect: "16:9",
    resolution: "720",
    captions: "none",
    visualFormat: "PRESENTER",
    channelTemplate: "default",
    script: "Across the world's remaining wetlands, small changes in water, temperature, and vegetation can decide whether a threatened species returns for another season. Conservation teams study those changes carefully, combining field observations with satellite data and long-term habitat records. Their work is patient rather than dramatic, but every restored nesting site and protected migration route creates another opportunity for wildlife to recover. The goal is not simply to preserve one remarkable bird. It is to protect the living system that supports thousands of connected species, including the communities that depend on healthy water and resilient landscapes.",
    visualDescription: "",
    needsAvatar: true,
  },
  story: {
    id: "story",
    title: "Make a visual story",
    eyebrow: "AI video",
    copy: "Write the story, describe the visuals, and add a presenter image. Aivatar handles the Higgsfield animation and final composition.",
    icon: "video",
    featured: true,
    aspect: "16:9",
    resolution: "1080",
    captions: "burned",
    visualFormat: "SPLIT",
    channelTemplate: "default",
    script: "Here is the idea in plain language, then a visual that makes the point land.",
    visualDescription: "A clean wide shot of a modern studio desk with soft daylight and a simple product on the table.",
    needsAvatar: true,
  },
  image: {
    id: "image",
    title: "Create a topic visual",
    eyebrow: "Image",
    copy: "Describe the visual, add narration, and export a short visual beat without a presenter.",
    icon: "image",
    aspect: "1:1",
    resolution: "1080",
    captions: "none",
    visualFormat: "FULL_VISUAL",
    channelTemplate: "presenter_no_captions",
    script: "A single strong image can carry the whole point if the framing stays simple.",
    visualDescription: "A quiet coastal laboratory at dusk, glass walls, warm practical lights, no people in frame.",
    needsAvatar: false,
  },
  presentation: {
    id: "presentation",
    title: "Shape a narrative deck",
    eyebrow: "Presentation",
    copy: "Write spoken beats for a captioned visual sequence you can later extend scene by scene.",
    icon: "slides",
    aspect: "16:9",
    resolution: "1080",
    captions: "burned",
    visualFormat: "FULL_VISUAL",
    channelTemplate: "default",
    script: "Today we will cover the problem, the change, and the result your audience should remember.",
    visualDescription: "A restrained title card with ample negative space and a single accent shape.",
    needsAvatar: false,
  },
  social: {
    id: "social",
    title: "Make a vertical social cut",
    eyebrow: "Social post",
    copy: "Choose a HeyGen presenter and export a captioned 9:16 clip for stories and shorts.",
    icon: "spark",
    aspect: "9:16",
    resolution: "1080",
    captions: "burned",
    visualFormat: "PRESENTER",
    channelTemplate: "default",
    script: "If you only remember one thing from this, make it this: start smaller than you think.",
    visualDescription: "",
    needsAvatar: true,
  },
};

export const WORKFLOWS: StudioPreset[] = [
  STUDIO_PRESETS.story,
  STUDIO_PRESETS.avatar,
  STUDIO_PRESETS.image,
  STUDIO_PRESETS.presentation,
  STUDIO_PRESETS.social,
];

export const TEMPLATES: Array<StudioPreset & { thumb: string; kind: string }> = [
  { ...STUDIO_PRESETS.story, title: "Documentary presenter", kind: "AI video", thumb: "thumb-video" },
  { ...STUDIO_PRESETS.avatar, title: "Expert explainer", kind: "Avatar video", thumb: "thumb-talk" },
  { ...STUDIO_PRESETS.social, title: "Vertical story", kind: "Social", thumb: "thumb-reel" },
  { ...STUDIO_PRESETS.image, title: "Product reveal", kind: "Visual", thumb: "thumb-product" },
];
