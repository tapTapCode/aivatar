from __future__ import annotations

from pathlib import Path

import yaml

from src.schemas.scene import OutputSpec
from src.schemas.templates import ChannelTemplate


class TemplateNotFoundError(FileNotFoundError):
    pass


class TemplateLoader:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def load(self, name: str, *, output: OutputSpec | None = None) -> ChannelTemplate:
        if not name or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in name
        ):
            raise ValueError("invalid template name")
        path = (self.root / f"{name}.yaml").resolve()
        if self.root not in path.parents or not path.is_file():
            raise TemplateNotFoundError(name)
        data = yaml.safe_load(path.read_text())
        template = ChannelTemplate.model_validate(data)
        if output and (template.width, template.height, template.fps) != (
            output.width,
            output.height,
            output.fps,
        ):
            # Project output is authoritative while styling remains template-controlled.
            template = template.model_copy(
                update={"width": output.width, "height": output.height, "fps": output.fps}
            )
        return template
