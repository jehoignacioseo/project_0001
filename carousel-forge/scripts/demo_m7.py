#!/usr/bin/env python
"""M7 완료 기준: 한국어 인스타그램 세트 → 중국어 샤오홍슈 세트 변환.

    export ANTHROPIC_API_KEY=...
    python scripts/demo_m7.py                       # 데모 세트를 현지화한다
    python scripts/demo_m7.py --state storage/m2/state.json   # M2 산출물을 쓴다
    python scripts/demo_m7.py --render              # 도착 캔버스로 실제 렌더까지

순서가 중요하다. 글자수 상한을 먼저 **실측**하고, 그 상한을 제약으로 걸어 현지화한다.
반대로 하면 "번역해 놓고 안 맞으면 줄인다"가 되는데, 그러면 중국어 문장이 한국어
문장의 그림자로 남는다.

  1. 도착 캔버스/폰트로 안전영역 수용량 실측      (core.render.capacity)
  2. StyleDNA 재조준 — 폰트·글자수·캡션 규격      (retarget_dna)
  3. 카피 현지화 + 제약 강제                      (A10)
  4. 해시태그 재조사 — 번역이 아니라 검색         (A10, 서버측 web_search)
  5. (--render) 도착 캔버스로 렌더해 실제로 들어가는지 확인
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.agents import Localizer  # noqa: E402
from core.agents.base import AgentContext  # noqa: E402
from core.agents.localizer import LocalizationError, cover_title_report, retarget_dna  # noqa: E402
from core.config import STORAGE_DIR, platform_spec  # noqa: E402
from core.platform.base import adapter_for  # noqa: E402
from core.render.capacity import SAMPLES, measure_capacity  # noqa: E402
from core.render.model import Theme  # noqa: E402
from tests.fixtures.demo_set import demo_copy, demo_style_dna  # noqa: E402


def load_source(state_path: Path | None) -> tuple[dict, dict]:
    if state_path and state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        dna = state.get("style_dna") or demo_style_dna()
        print(f"상태 파일에서 카피 {len(state['copy']['slides'])}장을 읽었다")
        return state["copy"], dna
    return demo_copy(), demo_style_dna()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", type=Path, default=None, help="M2 상태 파일")
    ap.add_argument("--source-platform", default="instagram")
    ap.add_argument("--target-platform", default="xiaohongshu")
    ap.add_argument("--target-language", default="zh")
    ap.add_argument("--parent-set-id", default="demo0001")
    ap.add_argument("--render", action="store_true", help="도착 캔버스로 실제 렌더까지 한다")
    ap.add_argument("--backgrounds", type=Path, default=STORAGE_DIR / "assets" / "demo" / "backgrounds")
    ap.add_argument("--out", type=Path, default=STORAGE_DIR / "m7")
    args = ap.parse_args()

    copy, dna = load_source(args.state)
    args.out.mkdir(parents=True, exist_ok=True)

    source_spec = platform_spec(args.source_platform)
    target_spec = platform_spec(args.target_platform)
    print(
        f"\n{source_spec.display_name} {source_spec.canvas.ratio} / {dna['copy']['language']}"
        f"  →  {target_spec.display_name} {target_spec.canvas.ratio} / {args.target_language}"
    )

    # ── 1. 수용량 실측 ──────────────────────────────────────────────────
    print("\n[1] 도착 캔버스에서 글자수 수용량을 실측한다 (어림하지 않는다)")
    probe_dna, _ = retarget_dna(
        dna,
        target_language=args.target_language,
        target_platform=args.target_platform,
    )
    theme = Theme.from_dna(probe_dna, target_spec, target_spec.canvas)
    sample = SAMPLES.get(args.target_language)
    if sample is None:
        print(f"  {args.target_language} 표본이 없다 — capacity 없이 진행한다", file=sys.stderr)
        capacity = {}
    else:
        capacity = measure_capacity(
            theme, target_spec.canvas, sample=sample, work_dir=args.out / "capacity"
        )
        for cap in capacity.values():
            print(f"    {cap}")

    # ── 2~4. 현지화 ─────────────────────────────────────────────────────
    ctx = AgentContext(
        account_id=args.parent_set_id,
        platform=args.source_platform,
        language=dna["copy"]["language"],
        style_dna=dna,
    )
    print("\n[2] StyleDNA 재조준 → [3] 카피 현지화 → [4] 해시태그 재조사")
    print("    해시태그 검색은 Anthropic 서버에서 돈다 — 이 컨테이너의 아웃바운드와 무관하다.")
    try:
        result = Localizer().localize(
            copy,
            ctx,
            target_platform=args.target_platform,
            target_language=args.target_language,
            parent_set_id=args.parent_set_id,
            capacity=capacity,
        )
    except LocalizationError as exc:
        print(f"\n현지화가 제약을 지키지 못했다:\n{exc}", file=sys.stderr)
        return 1

    print("\n" + "─" * 66)
    print(result.summary())
    print("─" * 66)

    print("\n원문 → 현지화:")
    source_blocks = {b["id"]: b["text"] for s in copy["slides"] for b in s["copy_blocks"]}
    for slide in result.copy["slides"]:
        print(f"\n  슬라이드 {slide['index']} [{slide['role']}] {slide['layout_template']}")
        for block in slide["copy_blocks"]:
            before = source_blocks[block["id"]].replace("\n", " ⏎ ")
            after = block["text"].replace("\n", " ⏎ ")
            print(f"    {block['role']:<12} {before}")
            print(f"    {'':<12} → {after}  ({len(after)}자 / 상한 {block['max_chars']}자)")

    print("\n커버 제목:")
    for line in cover_title_report(result.copy, args.target_platform):
        print(f"    {line}")

    adapter = adapter_for(args.target_platform)
    caption = result.copy["caption"]
    assembled = adapter.assemble_caption(
        caption["hook_line"], caption["body"], caption["cta"], result.copy["hashtags"]
    )
    print(f"\n조립된 캡션 ({len(assembled)}자 / 상한 {target_spec.caption_max_chars}자):")
    print("\n".join(f"    {line}" for line in assembled.splitlines()))

    print("\n재조사한 해시태그:")
    for tag in result.hashtag_research:
        print(f"    {adapter.format_tag(tag['tag'])}  [{tag['kind']}] {tag['evidence'][:70]}")

    (args.out / "localized.json").write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out / "caption.txt").write_text(assembled + "\n", encoding="utf-8")
    print(f"\n결과 → {args.out / 'localized.json'}")

    # ── 5. 도착 캔버스로 렌더 ───────────────────────────────────────────
    if args.render:
        print("\n[5] 도착 캔버스로 렌더한다 — 좌표는 여기서 처음부터 다시 실측된다")
        code = render_variant(result, args)
        if code:
            return code
    else:
        print("\n(--render를 붙이면 도착 캔버스로 실제 렌더까지 한다)")
    return 0


def render_variant(result, args) -> int:
    """현지화된 세트를 도착 캔버스로 렌더한다.

    좌표를 원본에서 옮겨 오지 않는다. 캔버스가 4:5에서 3:4로 바뀌었으므로 줄바꿈과
    베이스라인이 전부 달라지고, 그 값은 브라우저가 다시 재야만 맞는다 (절대 규칙 #3).
    """
    from core.render import render_and_export
    from core.render.model import RenderBlock, RenderSet, RenderSlide

    spec = platform_spec(result.platform)
    theme = Theme.from_dna(result.style_dna, spec, spec.canvas)
    backgrounds = sorted(args.backgrounds.glob("*.png")) if args.backgrounds.exists() else []
    if not backgrounds:
        print(
            f"  배경이 없다: {args.backgrounds}. "
            "`python scripts/make_dummy_backgrounds.py`로 만들 수 있다.",
            file=sys.stderr,
        )
        return 1

    slides = []
    for i, slide in enumerate(result.copy["slides"]):
        background = backgrounds[i % len(backgrounds)]
        slides.append(
            RenderSlide(
                index=slide["index"],
                role=slide["role"],
                layout_template=slide["layout_template"],
                background=background.name,
                blocks=[
                    RenderBlock(
                        id=b["id"],
                        role=b["role"],
                        text=b["text"],
                        max_chars=b.get("max_chars"),
                        emphasis_spans=[tuple(s) for s in b.get("emphasis_spans", [])],
                    )
                    for b in slide["copy_blocks"]
                ],
            )
        )

    render_set = RenderSet(
        set_id=f"{args.parent_set_id}_{result.language}",
        account=args.parent_set_id,
        platform=result.platform,
        language=result.language,
        theme=theme,
        slides=slides,
    )
    report = render_and_export(
        render_set,
        out_root=args.out / "exports",
        background_source_dir=args.backgrounds,
        style_dna=result.style_dna,
        caption=result.copy["caption"],
        hashtags=result.copy["hashtags"],
    )
    print(f"    캔버스 {spec.canvas.width}×{spec.canvas.height} ({spec.canvas.ratio})")
    print(f"    내보내기 → {report.export_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
