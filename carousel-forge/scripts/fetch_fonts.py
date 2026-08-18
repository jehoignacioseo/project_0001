#!/usr/bin/env python
"""렌더용 폰트를 내려받아 `core/render/fonts/`에 넣는다.

폰트는 `@font-face`로 로컬 임베드한다 — 웹폰트 네트워크 의존은 렌더 불일치의
원인이다. 상업적 사용이 가능한 폰트만 담는다 (절대 규칙 #10).

npm 레지스트리에서 패키지를 받아 필요한 파일만 꺼낸다. 네트워크가 막힌
환경이라면 같은 파일을 손으로 넣어도 된다.

    python scripts/fetch_fonts.py            # 한국어 세트 (Pretendard)
    python scripts/fetch_fonts.py --set zh   # 중국어 세트 (Noto Sans SC)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import FONTS_DIR  # noqa: E402

SETS: dict[str, dict] = {
    "ko": {
        "package": "pretendard",
        "license": "SIL OFL 1.1",
        "files": {
            "package/dist/web/static/woff2/Pretendard-Regular.woff2": "Pretendard-Regular.woff2",
            "package/dist/web/static/woff2/Pretendard-Bold.woff2": "Pretendard-Bold.woff2",
            "package/dist/web/static/woff2/Pretendard-ExtraBold.woff2": "Pretendard-ExtraBold.woff2",
            "package/dist/LICENSE.txt": "Pretendard-LICENSE.txt",
        },
    },
    "zh": {
        "package": "@fontsource/noto-sans-sc",
        "license": "SIL OFL 1.1",
        "files": {
            # @fontsource는 subset별로 파일이 쪼개져 있다. 전체 커버리지가 필요하므로
            # 실제로 어떤 파일을 쓸지는 M7(중국어 지원) 시점에 확정한다.
            "package/LICENSE": "NotoSansSC-LICENSE.txt",
        },
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", dest="which", choices=sorted(SETS), default="ko")
    ap.add_argument("--dest", type=Path, default=FONTS_DIR)
    args = ap.parse_args()

    config = SETS[args.which]
    args.dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        print(f"npm pack {config['package']} …")
        result = subprocess.run(
            ["npm", "pack", config["package"]],
            cwd=tmp_path, capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            print(f"npm pack 실패:\n{result.stderr}", file=sys.stderr)
            return 1
        tarballs = list(tmp_path.glob("*.tgz"))
        if not tarballs:
            print("받은 tarball이 없다", file=sys.stderr)
            return 1

        with tarfile.open(tarballs[0]) as tar:
            members = {m.name: m for m in tar.getmembers()}
            missing = [src for src in config["files"] if src not in members]
            if missing:
                print(f"패키지 안에 없는 파일: {missing}", file=sys.stderr)
                return 1
            for src, dst in config["files"].items():
                extracted = tar.extractfile(members[src])
                if extracted is None:
                    print(f"읽을 수 없다: {src}", file=sys.stderr)
                    return 1
                target = args.dest / dst
                with target.open("wb") as fh:
                    shutil.copyfileobj(extracted, fh)
                print(f"  {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}")

    print(f"완료. 라이선스: {config['license']} — 상업적 사용 가능.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
