#!/usr/bin/env python
"""JSON Schema → Pydantic 모델 + TypeScript 타입 생성.

`schemas/*.schema.json`이 단일 진실 소스다. 백엔드(Pydantic)와 Figma
플러그인(TypeScript)이 같은 계약을 보도록 여기서 한 번에 뽑아낸다.
손으로 수정하지 말 것 — 스키마를 고치고 이 스크립트를 다시 돌린다.

    python scripts/codegen.py            # 생성
    python scripts/codegen.py --check    # 생성물이 최신인지 확인만 (CI용)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
PY_OUT = ROOT / "apps" / "api" / "schemas" / "generated"
TS_OUT = ROOT / "apps" / "figma-plugin" / "src" / "generated"

BANNER_PY = '"""AUTO-GENERATED — do not edit. `python scripts/codegen.py`로 재생성한다.\n\nsource: schemas/{src}\n"""\n'
BANNER_TS = "// AUTO-GENERATED — do not edit. Regenerate with `python scripts/codegen.py`.\n// source: schemas/{src}\n"


# ── Pydantic ────────────────────────────────────────────────────────────────

def gen_pydantic(schema_path: Path, out_path: Path) -> str:
    from datamodel_code_generator import DataModelType, Formatter, InputFileType, PythonVersion, generate

    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "model.py"
        generate(
            schema_path.read_text(encoding="utf-8"),
            input_file_type=InputFileType.JsonSchema,
            input_filename=schema_path.name,
            output=tmp_out,
            output_model_type=DataModelType.PydanticV2BaseModel,
            target_python_version=PythonVersion.PY_311,
            use_schema_description=True,
            use_field_description=True,
            field_constraints=True,
            use_annotated=True,
            snake_case_field=False,
            capitalise_enum_members=True,
            disable_timestamp=True,
            formatters=[Formatter.BLACK, Formatter.ISORT],
        )
        body = tmp_out.read_text(encoding="utf-8")
    return BANNER_PY.format(src=schema_path.name) + "\n" + body


# ── TypeScript ──────────────────────────────────────────────────────────────

def _safe_comment(text: str) -> str:
    """주석 안에서 블록 주석을 닫아버리지 않도록 이스케이프."""
    return " ".join(text.split()).replace("*/", "*\\/")


class TsEmitter:
    """JSON Schema(draft 2020-12의 우리가 쓰는 부분집합) → TypeScript 선언.

    지원: object/array/enum/const/$ref(#/$defs/*)/타입 유니온/nullable.
    스키마에 없는 기능(oneOf, allOf, patternProperties …)을 만나면 조용히
    `unknown`으로 흘리지 않고 예외를 던진다 — 계약이 어긋난 채 생성되는 쪽이
    더 위험하기 때문이다.
    """

    def __init__(self, schema: dict):
        self.schema = schema
        self.defs: dict[str, dict] = schema.get("$defs", {})
        self.lines: list[str] = []

    def emit(self) -> str:
        root_name = self.schema.get("title") or "Root"
        for name, sub in self.defs.items():
            self._emit_named(sub.get("title", name), sub)
        self._emit_named(root_name, self.schema, root=True)
        return "\n".join(self.lines)

    def _emit_named(self, name: str, node: dict, root: bool = False) -> None:
        doc = node.get("description")
        if doc:
            self.lines.append("/** " + _safe_comment(doc) + " */")
        if node.get("type") == "object" or "properties" in node:
            self.lines.append(f"export interface {name} {{")
            self.lines.extend(self._object_members(node, indent="  "))
            self.lines.append("}")
        else:
            self.lines.append(f"export type {name} = {self._type(node)};")
        self.lines.append("")

    def _object_members(self, node: dict, indent: str) -> list[str]:
        out: list[str] = []
        required = set(node.get("required", []))
        for key, sub in (node.get("properties") or {}).items():
            desc = sub.get("description")
            if desc:
                out.append(indent + "/** " + _safe_comment(desc) + " */")
            opt = "" if key in required else "?"
            out.append(f"{indent}{key}{opt}: {self._type(sub, indent=indent)};")
        extra = node.get("additionalProperties")
        if extra is True:
            out.append(f"{indent}[key: string]: unknown;")
        elif isinstance(extra, dict):
            out.append(f"{indent}[key: string]: {self._type(extra, indent=indent)};")
        return out

    def _type(self, node: dict, indent: str = "") -> str:
        for unsupported in ("oneOf", "anyOf", "allOf", "not", "patternProperties"):
            if unsupported in node:
                raise NotImplementedError(
                    f"TS emitter가 지원하지 않는 키워드: {unsupported}. "
                    "스키마를 단순화하거나 emitter를 확장하라."
                )

        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                raise NotImplementedError(f"지원하지 않는 $ref: {ref}")
            key = ref.split("/")[-1]
            return self.defs.get(key, {}).get("title", key)

        if "const" in node:
            return json.dumps(node["const"])

        if "enum" in node:
            return " | ".join(json.dumps(v) for v in node["enum"])

        t = node.get("type")
        if t == "null":
            return "null"
        if isinstance(t, list):
            # ["object", "null"] 같은 nullable 유니온. null은 곧바로 리터럴로 접는다.
            parts = ["null" if one == "null" else self._type({**node, "type": one}, indent=indent) for one in t]
            return " | ".join(dict.fromkeys(parts))

        if t == "array":
            items = node.get("items")
            inner = self._type(items, indent=indent) if items else "unknown"
            tuple_len = node.get("minItems") == node.get("maxItems") and node.get("minItems")
            if tuple_len and tuple_len <= 4:
                return "[" + ", ".join([inner] * tuple_len) + "]"
            return f"Array<{inner}>"

        if t == "object" or "properties" in node:
            members = self._object_members(node, indent=indent + "  ")
            if not members:
                return "Record<string, unknown>"
            return "{\n" + "\n".join(members) + "\n" + indent + "}"

        return {
            "string": "string",
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
            "null": "null",
        }.get(t, "unknown")


def gen_typescript(schema_path: Path) -> str:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return BANNER_TS.format(src=schema_path.name) + "\n" + TsEmitter(schema).emit()


# ── driver ──────────────────────────────────────────────────────────────────

def targets() -> list[tuple[Path, Path, Path]]:
    out = []
    for schema in sorted(SCHEMA_DIR.glob("*.schema.json")):
        stem = schema.name[: -len(".schema.json")]
        out.append((schema, PY_OUT / f"{stem}.py", TS_OUT / f"{stem}.ts"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="재생성 대신 최신 여부만 확인")
    args = ap.parse_args()

    PY_OUT.mkdir(parents=True, exist_ok=True)
    TS_OUT.mkdir(parents=True, exist_ok=True)

    stale: list[str] = []
    py_modules: list[str] = []
    ts_modules: list[str] = []

    for schema, py_path, ts_path in targets():
        py_src = gen_pydantic(schema, py_path)
        ts_src = gen_typescript(schema)
        py_modules.append(py_path.stem)
        ts_modules.append(ts_path.stem)

        for path, src in ((py_path, py_src), (ts_path, ts_src)):
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current == src:
                continue
            if args.check:
                stale.append(str(path.relative_to(ROOT)))
            else:
                path.write_text(src, encoding="utf-8")
                print(f"  wrote {path.relative_to(ROOT)}")

    init_src = (
        '"""AUTO-GENERATED package index — do not edit."""\n\n'
        + "".join(f"from . import {m} as {m}  # noqa: F401\n" for m in sorted(py_modules))
    )
    index_src = BANNER_TS.format(src="*.schema.json") + "\n" + "".join(
        f'export * from "./{m}";\n' for m in sorted(ts_modules)
    )
    for path, src in ((PY_OUT / "__init__.py", init_src), (TS_OUT / "index.ts", index_src)):
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == src:
            continue
        if args.check:
            stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(src, encoding="utf-8")
            print(f"  wrote {path.relative_to(ROOT)}")

    if args.check and stale:
        print("생성물이 스키마와 어긋나 있다. `python scripts/codegen.py`를 실행하라:", file=sys.stderr)
        for s in stale:
            print(f"  - {s}", file=sys.stderr)
        return 1

    print("codegen OK" if not args.check else "codegen up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
