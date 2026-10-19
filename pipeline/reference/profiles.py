from __future__ import annotations

from copy import deepcopy

REFERENCE_DOCUMENTARY_V1 = {
    "id": "reference_documentary_v1",
    "name": "Reference Documentary v1",
    "status": "baseline",
    "source": "Agreed Aivatar/FaceTuber-style requirements; tune after side-by-side reference review.",
    "editorial": {
        "presenter_target": 0.30,
        "core_scene_types": ["PRESENTER", "SPLIT", "FULL_VISUAL"],
        "presenter_priority": [
            "opening_hook",
            "key_explanation",
            "major_transition",
            "important_argument",
            "personal_commentary",
            "cta",
            "conclusion",
        ],
        "preferred_scene_seconds": {"min": 4.0, "target": 6.0, "max": 10.0},
        "visual_density": 0.75,
    },
    "composition": {
        "split_default": "40/60",
        "split_options": ["50/50", "40/60", "35/65"],
        "presenter_sides": ["left", "right"],
        "pip_enabled": True,
        "rounded_presenter": True,
        "presenter_border": True,
        "animated_resizing": True,
    },
    "visuals": {
        "selection_order": ["cache", "motion_graphic", "flux_motion", "ltx_video"],
        "flux_model_family": "FLUX.2 Klein 4B",
        "ltx_model_family": "LTX 2.3",
        "ltx_policy": "selective_motion_only",
        "image_motion": [
            "slow_push_in",
            "slow_pull_out",
            "pan_left",
            "pan_right",
            "pan_up",
            "pan_down",
            "subtle_zoom",
            "document_focus",
            "static",
        ],
    },
    "graphics": {
        "density": "medium",
        "templates": ["title_card", "section_header", "highlight_keyword", "lower_third", "callout"],
        "captions": True,
        "transitions": "subtle",
    },
    "audio": {
        "master_narration_authoritative": True,
        "presenter_audio_in_final": False,
        "generated_broll_audio_in_final": False,
        "music_ducking": True,
    },
    "output": {"aspect_ratio": "16:9", "resolution": "1080p", "fps": 30, "format": "mp4"},
    "validation": {
        "requires_side_by_side_reference_review": True,
        "note": "This is the agreed production-format baseline, not a claim of measured pixel-level reference matching.",
    },
}


def list_reference_profiles() -> list[dict]:
    return [deepcopy(REFERENCE_DOCUMENTARY_V1)]


def get_reference_profile(profile_id: str) -> dict:
    if profile_id != REFERENCE_DOCUMENTARY_V1["id"]:
        raise KeyError(profile_id)
    return deepcopy(REFERENCE_DOCUMENTARY_V1)
