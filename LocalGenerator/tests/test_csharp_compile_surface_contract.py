from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_optional_real_tml_build_helper_is_present_and_skips_without_target():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/build/try_tml_build_check.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    assert "[SKIP]" in result.stdout or "[run]" in result.stdout


def test_tml_build_helper_discovers_windows_dotnet_exe_when_linux_dotnet_missing(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT))
    from tools.build import try_tml_build_check

    fake_dotnet = tmp_path / "dotnet.exe"
    fake_dotnet.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(try_tml_build_check.shutil, "which", lambda _name: None)

    resolved = try_tml_build_check.resolve_dotnet_command(extra_candidates=[fake_dotnet])

    assert resolved == str(fake_dotnet)


def test_tml_build_helper_converts_wsl_external_deps_for_windows_dotnet(monkeypatch):
    sys.path.insert(0, str(ROOT))
    from tools.build import try_tml_build_check

    calls = []

    def convert(command, **kwargs):
        calls.append((command, kwargs))
        return type("Proc", (), {"returncode": 0, "stdout": "C:\\deps\\tml\n"})()

    monkeypatch.setattr(try_tml_build_check.subprocess, "run", convert)

    value = try_tml_build_check.msbuild_path_value(
        Path("/home/xipong/tmp/tml-deps-src"),
        dotnet_cmd="/mnt/c/Program Files/dotnet/dotnet.exe",
    )

    assert value == "C:\\deps\\tml"
    assert calls == [(["wslpath", "-w", str(Path("/home/xipong/tmp/tml-deps-src").resolve())], {
        "text": True, "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
    })]


@pytest.mark.parametrize("log,mod,code,line", [
    pytest.param((
        'ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs(12,34): error CS0246: Missing type\n'
        'ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs(99,5): warning CS0168: unused\n'
    ), None, "CS0246", 12, id="roslyn"),
    pytest.param((
        '[12:52:39.459] [.NET TP Worker/ERROR] [tML]: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Items\\GeneratedItem.cs(593,32): error CS1061: "AccessorySpec" не содержит определения "SentrySlots".\n'
        'Error: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Items\\GeneratedItem.cs(593,32): error CS1061: "AccessorySpec" не содержит определения "SentrySlots".\n'
        '[12:52:39.461] [.NET TP Worker/WARN] [tML]: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Projectiles\\GeneratedProjectile.cs(50,19): warning CS0169: Поле "GeneratedProjectile._burstVisualTimer" никогда не используется.\n'
        '[12:52:39.462] [.NET TP Worker/ERROR] [tML]: C:\\OtherMod\\Broken.cs(1,1): error CS9999: irrelevant\n'
    ), "InfiniCrafterLocal", "CS1061", 593, id="tml-prefix-dedup-filter"),
])
def test_build_log_parser_retains_exact_diagnostics(log, mod, code, line):
    sys.path.insert(0, str(ROOT))
    from tools.build.parse_tml_build_log import parse_build_log

    summary = parse_build_log(log, mod=mod)
    assert summary["ok"] is False
    assert (summary["errorCount"], summary["warningCount"]) == (1, 1)
    assert (summary["errors"][0]["code"], summary["errors"][0]["line"]) == (code, line)
    assert "OtherMod" not in str(summary)


def _native_registration_issues(project, runner, sources):
    """One source-only registration gate; compilation/execution are separate gates."""
    from fnmatch import fnmatchcase
    import re
    import xml.etree.ElementTree as ET
    sys.path.insert(0, str(ROOT))
    from tools.checks.check_csharp_contracts import method_body, stripped

    compile_items = list(ET.fromstring(project).iter("Compile"))
    includes = [row.attrib.get("Include") for row in compile_items]
    issues = []
    if "$(InfiniModSourceRoot)/**/*.cs" not in includes:
        issues.append("canonical mod source is not compiled")
    compiled = [name for row in compile_items for pattern in row.attrib.get("Include", "").split(";")
                for name in sources if fnmatchcase(name, pattern)
                and not any(fnmatchcase(name, excluded) for excluded in row.attrib.get("Exclude", "").split(";"))]
    if len(compiled) != len(set(compiled)) or set(compiled) != set(sources):
        issues.append("native check sources must be compiled exactly once")
    body = stripped(method_body(runner, "RunChecks"), keep_strings=True)
    entries = re.findall(r'\(\s*"([^"\n]+)"\s*,\s*([^\n]+?)\)(?=\s*[,}])', body + ",")
    labels = [label for label, _ in entries]
    if not labels or len(labels) != len(set(labels)):
        issues.append("native runner labels must be nonempty and unique")
    code = "\n".join(stripped(sources[name]) for name in compiled)
    declared = set(re.findall(r"\b(?:public|private|internal)\s+static\s+void\s+(\w+)\s*\(", code))
    # Check actual direct registrations, not a second roster of private helpers.
    # Lambda/async call expressions are resolved by the real C# compiler.
    direct = {target.strip() for _, target in entries if re.fullmatch(r"\w+", target.strip())}
    if direct - declared:
        issues.append("registered native checks have no declaration: " + str(sorted(direct - declared)))
    return issues


def test_native_sources_compiled_once_and_registrations_resolve():
    sources = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "tools/native").glob("EngineRuntimeChecks*.cs")}
    assert _native_registration_issues((ROOT / "tools/native/EngineRuntimeChecks.csproj").read_text(), sources["EngineRuntimeChecks.cs"], sources) == []


@pytest.mark.parametrize("glob", [False, True])
@pytest.mark.parametrize("mutation", ["missing-compile", "duplicate-compile", "excluded-compile", "comment-registration", "missing-registration", "missing-method", "duplicate-label", "foreign-copy"])
def test_native_registration_gate_rejects_stranded_checks(mutation, glob):
    sources = {"EngineRuntimeChecks.cs": 'private static int RunChecks() { return 0; }',
               "EngineRuntimeChecks.Probe.cs": 'private static void Probe() { Real(); }'}
    runner = 'private static int RunChecks() { (string, Action)[] checks = { ("probe", Probe) }; return 0; }'
    test_compile = ('<Compile Include="EngineRuntimeChecks*.cs"/>' if glob else
                    '<Compile Include="EngineRuntimeChecks.cs"/><Compile Include="EngineRuntimeChecks.Probe.cs"/>')
    project = '<Project><ItemGroup><Compile Include="$(InfiniModSourceRoot)/**/*.cs"/>' + test_compile + '</ItemGroup></Project>'
    assert _native_registration_issues(project, runner, sources) == []
    renamed = {name: source.replace("Probe", "RenamedObserver") for name, source in sources.items()}
    assert _native_registration_issues(project, runner.replace("Probe)", "RenamedObserver)"), renamed) == []
    if mutation == "missing-compile":
        project = project.replace(test_compile, '<Compile Include="EngineRuntimeChecks.cs"/>')
    elif mutation == "duplicate-compile":
        project = project.replace('</ItemGroup>', '<Compile Include="EngineRuntimeChecks.Probe.cs"/></ItemGroup>')
    elif mutation == "excluded-compile":
        project = project.replace(test_compile, '<Compile Include="EngineRuntimeChecks*.cs" Exclude="EngineRuntimeChecks.Probe.cs"/>')
    elif mutation == "comment-registration":
        runner = runner.replace('("probe", Probe)', '/* ("probe", Probe) */')
    elif mutation == "missing-registration":
        runner = runner.replace('("probe", Probe)', '')
    elif mutation == "missing-method":
        sources["EngineRuntimeChecks.Probe.cs"] = '// private static void Probe() { Real(); }'
    elif mutation == "duplicate-label":
        runner = runner.replace('("probe", Probe)', '("probe", Probe), ("probe", Probe)')
    else:
        project = project.replace('$(InfiniModSourceRoot)/**/*.cs', 'copied-models/**/*.cs')
    assert _native_registration_issues(project, runner, sources)


def test_native_registration_glob_discovers_new_partial_without_project_edit():
    project = '<Project><ItemGroup><Compile Include="$(InfiniModSourceRoot)/**/*.cs"/><Compile Include="EngineRuntimeChecks*.cs"/></ItemGroup></Project>'
    runner = 'private static int RunChecks() { (string, Action)[] checks = { ("probe", Probe), ("new", AddedCheck) }; return 0; }'
    sources = {"EngineRuntimeChecks.cs": runner,
               "EngineRuntimeChecks.Probe.cs": 'private static void Probe() { Real(); }'}
    assert _native_registration_issues(project, runner, sources)
    sources["EngineRuntimeChecks.NewPartial.cs"] = 'private static void AddedCheck() { RealNewBoundary(); }'
    assert _native_registration_issues(project, runner, sources) == []
