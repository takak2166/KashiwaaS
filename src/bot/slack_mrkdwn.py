"""
Convert GitHub-flavored Markdown (and CommonMark) to Slack mrkdwn for chat.postMessage text.

Slack uses a limited mrkdwn dialect; this module maps common Markdown constructs to it.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, Literal, Optional

from mistune import Markdown
from mistune.block_parser import BlockParser
from mistune.core import BlockState
from mistune.plugins import import_plugin
from mistune.plugins.speedup import PARAGRAPH, parse_paragraph
from mistune.renderers._list import render_list
from mistune.renderers.html import HTMLRenderer
from mistune.util import escape as escape_text
from mistune.util import striptags


class SlackMrkdwnBlockParser(BlockParser):
    """BlockParser with paragraph splitting (from speedup) so lists and blocks parse correctly."""

    def __init__(self) -> None:
        super().__init__()
        self.register("paragraph", PARAGRAPH, parse_paragraph, before="blank_line")


class SlackMrkdwnRenderer(HTMLRenderer):
    """Renders parsed Markdown tokens as Slack mrkdwn (not HTML)."""

    # Must stay "html" so mistune plugins (table, strikethrough) register renderers on this instance.
    NAME: ClassVar[Literal["html"]] = "html"

    def render_token(self, token: Dict[str, Any], state: BlockState) -> str:
        if token["type"] == "list":
            return render_list(self, token, state)
        return super().render_token(token, state)

    def strong(self, text: str) -> str:
        return "*" + text + "*"

    def emphasis(self, text: str) -> str:
        return "_" + text + "_"

    def link(self, text: str, url: str, title: Optional[str] = None) -> str:
        safe = self.safe_url(url)
        if title:
            text = text + " (" + title + ")"
        return "<" + safe + "|" + text + ">"

    def image(self, text: str, url: str, title: Optional[str] = None) -> str:
        src = self.safe_url(url)
        alt = escape_text(striptags(text))
        label = alt or "image"
        if title:
            label = label + " (" + title + ")"
        return "<" + src + "|" + label + ">"

    def codespan(self, text: str) -> str:
        inner = text.replace("`", "'")
        return "`" + inner + "`"

    def linebreak(self) -> str:
        return "\n"

    def softbreak(self) -> str:
        return "\n"

    def paragraph(self, text: str) -> str:
        return text + "\n\n"

    def heading(self, text: str, level: int, **attrs: Any) -> str:
        return "*" + text + "*\n\n"

    def thematic_break(self) -> str:
        return "────────\n\n"

    def block_text(self, text: str) -> str:
        return text

    def block_code(self, code: str, info: Optional[str] = None) -> str:
        fence = "```"
        if info is not None:
            lang = info.strip().split(None, 1)[0]
            if lang:
                fence += lang
        return fence + "\n" + code.rstrip("\n") + "\n```\n\n"

    def block_quote(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            if line.strip():
                lines.append("> " + line)
            else:
                lines.append(">")
        return "\n".join(lines) + "\n\n"


def _render_strikethrough_slack(renderer: HTMLRenderer, text: str) -> str:
    return "~" + text + "~"


def _render_table_slack(renderer: HTMLRenderer, text: str) -> str:
    return text.strip() + "\n\n"


def _render_table_head_slack(renderer: HTMLRenderer, text: str) -> str:
    return text.rstrip() + "\n"


def _render_table_body_slack(renderer: HTMLRenderer, text: str) -> str:
    return text


def _render_table_row_slack(renderer: HTMLRenderer, text: str) -> str:
    return text.rstrip() + "\n"


def _render_table_cell_slack(
    renderer: HTMLRenderer, text: str, align: Optional[str] = None, head: bool = False
) -> str:
    cell = text.strip()
    if head:
        cell = "*" + cell + "*"
    return cell + " | "


def _build_markdown() -> Markdown:
    renderer = SlackMrkdwnRenderer(escape=False)
    md = Markdown(
        block=SlackMrkdwnBlockParser(),
        renderer=renderer,
        plugins=[
            import_plugin("strikethrough"),
            import_plugin("table"),
            import_plugin("url"),
        ],
    )
    md.renderer.register("strikethrough", _render_strikethrough_slack)
    md.renderer.register("table", _render_table_slack)
    md.renderer.register("table_head", _render_table_head_slack)
    md.renderer.register("table_body", _render_table_body_slack)
    md.renderer.register("table_row", _render_table_row_slack)
    md.renderer.register("table_cell", _render_table_cell_slack)
    return md


_markdown_converter: Optional[Markdown] = None


def markdown_to_slack_mrkdwn(text: str) -> str:
    """
    Convert Markdown text to Slack mrkdwn.

    On parse failure, returns the original string so the bot still posts something useful.
    """
    global _markdown_converter
    if not text:
        return text
    if _markdown_converter is None:
        _markdown_converter = _build_markdown()
    try:
        out = _markdown_converter(text)
        return out.strip()
    except Exception:
        return text
