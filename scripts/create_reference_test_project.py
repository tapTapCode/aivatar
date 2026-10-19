#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _BootstrapPath

ROOT = _BootstrapPath(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
from pathlib import Path

from sqlalchemy import select

from pipeline.core.config import settings
from pipeline.models.entities import Avatar, Channel, Project
from pipeline.reference.profiles import get_reference_profile
from pipeline.storage.db import SessionLocal
from pipeline.storage.migrate import migrate

DEFAULT_SCRIPT = """The fastest way to understand a complex story is to separate what changed from what merely looks new. In this short reference test, the presenter opens the argument, visuals take over for the supporting context, and the presenter returns only when the explanation benefits from a human face. The goal is not to fill every second with generated motion. It is to keep the pacing deliberate, the visuals relevant, and the narration continuous. When a still image can communicate the idea, Aivatar can add controlled camera movement locally. When genuine motion materially improves the scene, the Director can reserve a short LTX generation. Split-screen and picture-in-picture should clarify the story rather than decorate it. By the conclusion, the viewer should feel like they watched one edited documentary, not several AI tools stitched together."""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first 60–90 second Aivatar reference-test project.")
    parser.add_argument("--channel", default="Reference Test Channel")
    parser.add_argument("--avatar-name", default="Reference Presenter")
    parser.add_argument("--provider-avatar-id")
    parser.add_argument("--reference-image")
    parser.add_argument("--script-file")
    parser.add_argument("--duration", type=float, default=75.0)
    parser.add_argument("--voice-provider", choices=["ai33", "69labs", "imported_audio"], default="ai33")
    args = parser.parse_args()

    migrate()
    profile = get_reference_profile(settings.aivatar_reference_profile)
    script = Path(args.script_file).read_text(encoding="utf-8") if args.script_file else DEFAULT_SCRIPT

    with SessionLocal() as db:
        channel = db.scalar(select(Channel).where(Channel.name == args.channel))
        if channel is None:
            channel = Channel(
                name=args.channel,
                style_preset=profile["id"],
                aspect_ratio=profile["output"]["aspect_ratio"],
                resolution=profile["output"]["resolution"],
                settings_json={"reference_profile": profile},
            )
            db.add(channel); db.commit(); db.refresh(channel)

        avatar = db.scalar(select(Avatar).where(Avatar.channel_id == channel.id, Avatar.name == args.avatar_name))
        if avatar is None:
            avatar = Avatar(
                channel_id=channel.id,
                name=args.avatar_name,
                presenter_provider="authorized_higgsfield",
                provider_avatar_id=args.provider_avatar_id,
                reference_image_path=args.reference_image,
                voice_provider=args.voice_provider,
                settings_json={"reference_profile_id": profile["id"]},
            )
            db.add(avatar); db.commit(); db.refresh(avatar)
        else:
            if args.provider_avatar_id:
                avatar.provider_avatar_id = args.provider_avatar_id
            if args.reference_image:
                avatar.reference_image_path = args.reference_image
            avatar.voice_provider = args.voice_provider
            db.commit(); db.refresh(avatar)

        project = Project(
            channel_id=channel.id,
            avatar_id=avatar.id,
            name="Real Reference Test #1",
            script=script,
            state="CREATED",
            expected_duration=args.duration,
            presenter_target=profile["editorial"]["presenter_target"],
            resolution=profile["output"]["resolution"],
            aspect_ratio=profile["output"]["aspect_ratio"],
            budget_usd=settings.aivatar_default_project_budget_usd,
            visual_density=profile["editorial"]["visual_density"],
        )
        db.add(project); db.commit(); db.refresh(project)
        print(f"Created project {project.id}")
        print(f"Channel: {channel.name}")
        print(f"Avatar: {avatar.name}")
        print(f"Profile: {profile['name']}")
        print(f"Duration target: {project.expected_duration:.0f}s")
        print("Next: configure fresh providers, run the activation check, then generate narration/plan/assets/presenter/render from the desktop app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
