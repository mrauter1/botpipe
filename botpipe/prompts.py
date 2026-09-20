"""Inline and file prompts, with strict explicit template inputs."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Prompt:
    text: str | None = None
    path: str | None = None

    @classmethod
    def inline(cls, text):
        return cls(text=str(text))

    @classmethod
    def file(cls, path):
        return cls(path=str(path))

    def render(self, input=None):
        from .runtime import current_run

        ctx = current_run()
        if self.path is not None:
            path = Path(self.path)
            if not path.is_absolute():
                path = ctx.source_dir / path
            text = ctx.operation(
                "prompt",
                {"path": str(path)},
                lambda: path.read_text(encoding="utf-8"),
                retry_safe=True,
            )
        else:
            text = self.text or ""
        if "{{" in text or "{%" in text:
            from jinja2 import Environment, StrictUndefined

            text = (
                Environment(undefined=StrictUndefined, autoescape=False)
                .from_string(text)
                .render(
                    input=input,
                    run={
                        "id": ctx.run_id,
                        "folder": str(ctx.folder),
                        "task_id": ctx.task_id,
                        "workspace": str(ctx.workspace),
                    },
                )
            )
        return text
