"""Small lint-tool contracts. Product behavior belongs to Python/native consumers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def gates():
    modules = []
    for name in ("check_project_hygiene", "check_csharp_contracts"):
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def python_sources(source):
    return {"LocalGenerator/infini_local/pipelines/pipeline_runtime_constants.py": "BAD_NAME_PATTERNS = ()\n",
            "LocalGenerator/infini_local/renamed_probe.py": source}


@pytest.mark.parametrize("source,code", [
    ('values = {"name": 1, "name": 2}', "duplicate_dict_key"),
    ('def f():\n    x = 1\n    x = 1', "duplicate_assignment"),
    ('__all__ = [name for name in globals()]', "dynamic_exports"),
    ('import os as system\nx = system.environ.get("INFINI_DIRECT")', "raw_environment_read"),
    ('from os import getenv as read_env\nx = read_env("INFINI_DIRECT")', "raw_environment_read"),
    ('BAD_NAME_PATTERNS = ()', "constant_owner"),
])
def test_python_lint_reports_invalid_source(gates, source, code):
    hygiene, _ = gates
    assert any(issue.startswith(code + ":") for issue in hygiene.python_source_issues(python_sources(source)))


def test_python_lint_accepts_decoys_and_reports_import_cycle(gates):
    hygiene, _ = gates
    sources = python_sources('# os.getenv("COMMENT")\nimport os\nsnapshot = os.environ.copy()')
    assert hygiene.python_source_issues(sources) == []
    sources.update({"LocalGenerator/infini_local/a.py": "import infini_local.b",
                    "LocalGenerator/infini_local/b.py": "value = 1"})
    assert hygiene.python_source_issues(sources) == []
    sources["LocalGenerator/infini_local/b.py"] = "import infini_local.a"
    assert any(issue.startswith("import_cycle:") for issue in hygiene.python_source_issues(sources))


@pytest.mark.parametrize("path,source,code", [
    ("Common/Models/GeneratedItemData.Renamed.cs", "public string Tooltip { get; set; }", "authored_tooltip"),
    ("Common/Models/GeneratedItemData.Apply.cs", "item.useStyle = 0;", "numeric_sentinel"),
    ("Renamed.cs", "#pragma warning disable CS0246", "warning_suppression"),
])
def test_csharp_lint_reports_invalid_source_not_comment_or_string_decoys(gates, path, source, code):
    _, scanner = gates
    decoy = "// " + source + "\nstring text = " + json.dumps(source) + ";"
    assert scanner.source_policy_issues({path: decoy}) == []
    assert any(issue.startswith(code + ":") for issue in scanner.source_policy_issues({path: source}))


def test_forbidden_gameplay_router_policy_ignores_layout_and_decoys(gates):
    _, scanner = gates
    assert scanner.architecture_issues({"Moved.cs": '// AttackSpec\nstring text = "WeaponFamily";'}) == []
    assert scanner.architecture_issues({"Moved.cs": "class AttackSpec {}"}) == [
        "forbidden_gameplay_router:Moved.cs:AttackSpec"]


@pytest.mark.parametrize("filename,document,diagnostic", [
    ("author_item_response.schema.json", {"properties": {"tooltip": {}}}, "forbidden_author_field"),
    ("visual_runtime_entities.schema.json", {"properties": {"impactPrompt": {}}}, "foreign_visual_prompt"),
    ("vfx_runtime_events.schema.json", {"properties": {"spritePrompt": {}}}, "missing_vfx_prompt"),
])
def test_authored_language_policy_reports_schema_input(gates, filename, document, diagnostic):
    hygiene, _ = gates
    issues = hygiene.authored_contract_issues({"contracts/schemas/" + filename: json.dumps(document)})
    assert any(issue.startswith(diagnostic + ":") for issue in issues)


def test_repository_source_policies_pass(gates):
    hygiene, scanner = gates
    sources = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8-sig")
               for directory in (ROOT / "LocalGenerator/infini_local", ROOT / "tools") for p in directory.rglob("*.py")}
    assert hygiene.python_source_issues(sources) == []
    schemas = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
               for p in (ROOT / "contracts/schemas").glob("*.json")}
    assert hygiene.authored_contract_issues(schemas) == []
    assert scanner.main() == 0


def test_nullable_bound_scanner_handles_synthetic_valid_and_invalid_setters():
    from infini_local.qa.primitive_loss_audit import nullable_number_rejection_bounds
    source = b"""class MovedDto {
        private float? _value;
        public float? RenamedProperty {
            get => _value;
            set {
                if (value is not float amount || !float.IsFinite(amount) || amount < -2f || amount > 5f)
                    throw new InvalidDataException("range");
                _value = amount;
            }
        }
    }"""
    assert nullable_number_rejection_bounds(source, "MovedDto", "RenamedProperty") == [-2, 5]
    assert nullable_number_rejection_bounds(source.replace(b"_value = amount;", b"_value = 0f;"), "MovedDto", "RenamedProperty") is None
    assert nullable_number_rejection_bounds(source.replace(b"!float.IsFinite(amount) || ", b""), "MovedDto", "RenamedProperty") is None


def test_dto_inventory_reads_synthetic_properties_not_comments_or_constants():
    from infini_local.qa.primitive_loss_audit import _class_properties
    source = b"""class RenamedDto {
        public const string Decoy = "ignored";
        // public int Missing { get; set; }
        public string Name { get; set; }
        public int Count { get; init; }
    }"""
    assert _class_properties(source, "RenamedDto") == {"Name", "Count"}


def test_packet_collision_is_reported(gates, monkeypatch):
    _, scanner = gates
    monkeypatch.setattr(scanner, "read", lambda _: "public const byte SyncGeneratedProjectileVfxEvent = 9; public const byte Other = 9;")
    scanner.ERRORS.clear()
    scanner.check_packet_ids()
    assert any(issue.startswith("packet id collision:") for issue in scanner.ERRORS)
    scanner.ERRORS.clear()
