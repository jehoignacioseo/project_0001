"""JSON Schema가 단일 진실 소스다. 생성물이 뒤처지면 실패한다."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def test_generated_types_are_up_to_date():
    result = subprocess.run(
        [sys.executable, "scripts/codegen.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("path", sorted(SCHEMA_DIR.glob("*.schema.json")), ids=lambda p: p.name)
def test_schemas_are_valid_json_schema(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_every_schema_has_python_and_typescript_output():
    for path in SCHEMA_DIR.glob("*.schema.json"):
        stem = path.name[: -len(".schema.json")]
        assert (ROOT / "apps/api/schemas/generated" / f"{stem}.py").exists()
        assert (ROOT / "apps/figma-plugin/src/generated" / f"{stem}.ts").exists()


def test_demo_style_dna_satisfies_the_schema():
    schema = json.loads((SCHEMA_DIR / "style_dna.schema.json").read_text(encoding="utf-8"))
    dna = json.loads((ROOT / "tests/fixtures/style_dna_demo.json").read_text(encoding="utf-8"))
    jsonschema.validate(dna, schema)


def test_style_dna_rejects_non_hex_palette():
    schema = json.loads((SCHEMA_DIR / "style_dna.schema.json").read_text(encoding="utf-8"))
    dna = json.loads((ROOT / "tests/fixtures/style_dna_demo.json").read_text(encoding="utf-8"))
    dna["visual"]["palette"]["background"] = ["dark grey"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dna, schema)
