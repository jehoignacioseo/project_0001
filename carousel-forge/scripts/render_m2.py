"""M2 산출물(구조 + 카피) → M1 RenderSet.

두 마일스톤을 잇는 어댑터다. M2의 CopyBlock과 M1의 RenderBlock이 같은 계약
위에 있는지 여기서 드러난다 — 변환이 복잡해진다면 계약이 어긋난 것이다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.agents.base import AgentContext
from core.config import platform_spec
from core.render import RenderReport, render_and_export
from core.render.model import RenderBlock, RenderSet, RenderSlide, Theme


def render_set_from_m2(
    state: dict[str, Any], ctx: AgentContext, *, set_id: str = "m2demo", account: str = "demo"
) -> RenderSet:
    dna = ctx.style_dna
    spec = platform_spec(ctx.platform)
    theme = Theme.from_dna(dna, spec, spec.canvas)

    slides = []
    for slide in state["copy"]["slides"]:
        slides.append(
            RenderSlide(
                index=slide["index"],
                role=slide["role"],
                layout_template=slide["layout_template"],
                # A7 ArtDirector(M4)가 붙기 전까지 배경은 팔레트 단색으로 둔다.
                # 텍스트와 배경이 분리돼 있으므로 나중에 배경만 갈아 끼우면 된다.
                background_fill=theme.palette_background,
                blocks=[
                    RenderBlock(
                        id=b["id"],
                        role=b["role"],
                        text=b["text"],
                        max_chars=b["max_chars"],
                        emphasis_spans=[tuple(s) for s in b.get("emphasis_spans", [])],
                    )
                    for b in slide["copy_blocks"]
                ],
            )
        )

    return RenderSet(
        set_id=set_id,
        account=account,
        platform=ctx.platform,
        language=ctx.language,
        theme=theme,
        slides=slides,
    )


def render_from_m2(
    state: dict[str, Any],
    ctx: AgentContext,
    *,
    out_root: Path,
    set_id: str = "m2demo",
    account: str = "demo",
) -> RenderReport:
    render_set = render_set_from_m2(state, ctx, set_id=set_id, account=account)
    return render_and_export(
        render_set,
        out_root=out_root,
        style_dna=ctx.style_dna,
        caption=state["copy"]["caption"],
        hashtags=state["copy"]["hashtags"],
    )
