"""텍스트 수용량 실측 — "이 폰트로 이 폭에 몇 글자가 들어가는가".

A10이 언어를 바꾸면 글자수 상한을 다시 잡아야 한다. 그 상한을 어림으로 정하면
절대 규칙 #3(좌표를 추정하지 않는다)을 글자수 쪽에서 어기는 셈이다. 그래서 여기서
실제로 렌더해 보고 센다.

구하는 값은 두 가지다.

  chars_per_line  안전영역 폭 안에서 **한 줄에 들어가는 글자 수**
  chars           chars_per_line × text_block_max_lines = 그 역할의 물리적 상한

이 값은 계정의 문체 상한(StyleDNA의 headline_char_limit)과 별개다. 최종 상한은
둘 중 작은 쪽이다 — 문체가 허용해도 자리가 없으면 넘치고, 자리가 남아도 문체를
벗어나면 그 계정의 카피가 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from core.config import Canvas
from core.render.html_renderer import RenderError, chromium_executable
from core.render.model import FONT_FILES, Theme, TypeStyle

#: 역할별 대표 표본. 한자·한글 모두 폭이 대체로 일정하지만 완전히 같지는 않아서
#: (구두점·괄호는 좁다) 실제로 쓰일 법한 글자를 섞어 재는 편이 정확하다.
SAMPLES: dict[str, str] = {
    "ko": "집중이끊기는건의지탓이아니라책상탓입니다오늘부터딱하나만바꿔보세요",
    "zh": "专注力被打断不是意志力的问题而是桌面的问题今天只改一件事就够了",
}

_PROBE_JS = """
() => {
  const probe = document.getElementById('probe');
  const text = probe.firstChild;
  const range = document.createRange();
  const tops = [];
  for (let i = 0; i < text.length; i++) {
    range.setStart(text, i);
    range.setEnd(text, i + 1);
    const rect = range.getBoundingClientRect();
    tops.push(Math.round(rect.top * 100) / 100);
  }
  const first = tops[0];
  let count = 0;
  while (count < tops.length && tops[count] === first) count += 1;
  return { chars_per_line: count, measured: tops.length, box: probe.getBoundingClientRect().width };
}
"""


@dataclass(frozen=True)
class RoleCapacity:
    """한 역할(headline/body/…)이 안전영역 안에 담을 수 있는 글자 수."""

    role: str
    chars_per_line: int
    max_lines: int
    line_width_px: float

    @property
    def chars(self) -> int:
        return self.chars_per_line * self.max_lines

    def __str__(self) -> str:
        return (
            f"{self.role}: 한 줄 {self.chars_per_line}자 × {self.max_lines}줄 "
            f"= {self.chars}자 (폭 {self.line_width_px:.0f}px)"
        )


class CapacityError(RenderError):
    """수용량을 잴 수 없다. 짐작한 값으로 대신하지 않는다."""


def _probe_html(style: TypeStyle, width_px: float, sample: str) -> str:
    faces = []
    for (family, style_name), filename in FONT_FILES.items():
        if family != style.family and family not in style.fallback:
            continue
        path = Path(__file__).parent / "fonts" / filename
        if not path.exists():
            raise CapacityError(f"폰트 파일이 없다: {path}")
        weight = {"Regular": 400, "Medium": 500, "SemiBold": 600, "Bold": 700, "ExtraBold": 800}[
            style_name
        ]
        faces.append(
            f'@font-face {{ font-family: "{family}"; src: url("{path.as_uri()}") '
            f'format("woff2"); font-weight: {weight}; font-style: normal; font-display: block; }}'
        )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><style>\n"
        + "\n".join(faces)
        + "\nbody { margin: 0; }\n"
        + "#probe {\n"
        + f"  width: {width_px}px;\n"
        + f"  font-family: {style.css_font_family};\n"
        + f"  font-weight: {style.weight};\n"
        + f"  font-size: {style.size_px}px;\n"
        + f"  letter-spacing: {style.letter_spacing_em}em;\n"
        + f"  line-height: {style.line_height};\n"
        + "  word-break: break-word;\n"
        + "}\n</style></head><body>"
        + f'<div id="probe">{sample}</div></body></html>'
    )


def measure_capacity(
    theme: Theme,
    canvas: Canvas,
    *,
    sample: str,
    work_dir: Path,
    roles: tuple[str, ...] = ("headline", "body", "eyebrow"),
) -> dict[str, RoleCapacity]:
    """역할별 수용량을 실측한다. 표본이 한 줄보다 짧으면 실패한다."""
    if not sample:
        raise CapacityError("표본 문자열이 비어 있다")
    width = canvas.width - 2 * theme.safe_margin_px
    if width <= 0:
        raise CapacityError(f"안전영역 폭이 0 이하다: {width}px")

    work_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, RoleCapacity] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chromium_executable())
        page = browser.new_page(viewport={"width": canvas.width, "height": canvas.height})
        try:
            for role in roles:
                style = theme.style_for(role)
                path = work_dir / f"capacity_{role}.html"
                path.write_text(_probe_html(style, width, sample), encoding="utf-8")
                page.goto(path.as_uri(), wait_until="load")
                page.wait_for_function("document.fonts.status === 'loaded'")
                broken = page.evaluate(
                    "() => [...document.fonts].filter(f => f.status === 'error')"
                    ".map(f => f.family)"
                )
                if broken:
                    raise CapacityError(
                        f"@font-face 로드 실패: {', '.join(broken)}. 폴백 폰트로 잰 "
                        "수용량은 실제와 다르다."
                    )
                measured: dict[str, Any] = page.evaluate(_PROBE_JS)
                # 표본이 한 줄에 다 들어가면 "한 줄에 몇 자"를 잰 게 아니라 "표본이
                # 몇 자"를 잰 것이다. 줄이 넘칠 때까지 표본을 늘려 다시 잰다 —
                # 길이를 계산으로 정하면 그 순간 추정이 된다.
                repeat = 1
                while measured["chars_per_line"] >= measured["measured"] and repeat < 16:
                    repeat *= 2
                    path.write_text(
                        _probe_html(style, width, sample * repeat), encoding="utf-8"
                    )
                    page.goto(path.as_uri(), wait_until="load")
                    page.wait_for_function("document.fonts.status === 'loaded'")
                    measured = page.evaluate(_PROBE_JS)
                if measured["chars_per_line"] >= measured["measured"]:
                    raise CapacityError(
                        f"{role}: 표본을 {repeat}배로 늘려도 한 줄에 다 들어간다. "
                        "안전영역 폭이나 폰트 크기가 잘못됐을 수 있다."
                    )
                out[role] = RoleCapacity(
                    role=role,
                    chars_per_line=int(measured["chars_per_line"]),
                    max_lines=theme.text_block_max_lines,
                    line_width_px=float(measured["box"]),
                )
        finally:
            browser.close()
    return out
