from pathlib import Path
import subprocess
import sys

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def _check_static_csharp_compile_surface_scanner_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/check_csharp_contracts.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout


def _check_optional_real_tml_build_helper_is_present_and_skips_without_target():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/try_tml_build_check.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    assert "[SKIP]" in result.stdout or "[run]" in result.stdout


def _check_tml_build_helper_discovers_windows_dotnet_exe_when_linux_dotnet_missing(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import try_tml_build_check

    fake_dotnet = tmp_path / "dotnet.exe"
    fake_dotnet.write_text("fake", encoding="utf-8")
    monkeypatch.setattr(try_tml_build_check.shutil, "which", lambda _name: None)

    resolved = try_tml_build_check.resolve_dotnet_command(extra_candidates=[fake_dotnet])

    assert resolved == str(fake_dotnet)


def _check_tml_build_helper_converts_wsl_external_deps_for_windows_dotnet(monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import try_tml_build_check

    monkeypatch.setattr(
        try_tml_build_check.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Proc", (), {"returncode": 0, "stdout": "C:\\deps\\tml\n"})(),
    )

    value = try_tml_build_check.msbuild_path_value(
        Path("/home/xipong/tmp/tml-deps-src"),
        dotnet_cmd="/mnt/c/Program Files/dotnet/dotnet.exe",
    )

    assert value == "C:\\deps\\tml"


def _check_tml_build_helper_converts_wsl_project_for_windows_dotnet(monkeypatch):
    sys.path.insert(0, str(ROOT / "tools"))
    import try_tml_build_check

    monkeypatch.setattr(
        try_tml_build_check.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Proc", (), {"returncode": 0, "stdout": "C:\\repo\\Mod.csproj\n"})(),
    )

    value = try_tml_build_check.msbuild_path_value(
        Path("/home/xipong/project/Mod.csproj"),
        dotnet_cmd="/mnt/c/Program Files/dotnet/dotnet.exe",
    )

    assert value == "C:\\repo\\Mod.csproj"


def _check_tml_build_log_parser_extracts_roslyn_errors_and_warnings():
    sys.path.insert(0, str(ROOT / "tools"))
    from parse_tml_build_log import parse_build_log

    summary = parse_build_log(
        "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs(12,34): error CS0246: Missing type\n"
        "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs(99,5): warning CS0168: unused\n"
    )
    assert summary["ok"] is False
    assert summary["errorCount"] == 1
    assert summary["warningCount"] == 1
    assert summary["errors"][0]["code"] == "CS0246"


def _check_tml_build_log_parser_handles_tml_client_log_prefixes_and_dedupes():
    sys.path.insert(0, str(ROOT / "tools"))
    from parse_tml_build_log import parse_build_log

    log = (
        '[12:52:39.459] [.NET TP Worker/ERROR] [tML]: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Items\\GeneratedItem.cs(593,32): error CS1061: "AccessorySpec" не содержит определения "SentrySlots".\n'
        'Error: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Items\\GeneratedItem.cs(593,32): error CS1061: "AccessorySpec" не содержит определения "SentrySlots".\n'
        '[12:52:39.461] [.NET TP Worker/WARN] [tML]: C:\\Users\\Cosmi\\OneDrive\\Документы\\My Games\\Terraria\\tModLoader\\ModSources\\InfiniCrafterLocal\\Content\\Projectiles\\GeneratedProjectile.cs(50,19): warning CS0169: Поле "GeneratedProjectile._burstVisualTimer" никогда не используется.\n'
        '[12:52:39.462] [.NET TP Worker/ERROR] [tML]: C:\\OtherMod\\Broken.cs(1,1): error CS9999: irrelevant\n'
    )
    summary = parse_build_log(log, mod="InfiniCrafterLocal")
    assert summary["ok"] is False
    assert summary["errorCount"] == 1
    assert summary["warningCount"] == 1
    assert summary["errors"][0]["code"] == "CS1061"
    assert summary["errors"][0]["line"] == 593
    assert "OtherMod" not in str(summary)

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_static_csharp_compile_surface_scanner_passes',
    '_check_optional_real_tml_build_helper_is_present_and_skips_without_target',
    '_check_tml_build_helper_discovers_windows_dotnet_exe_when_linux_dotnet_missing',
    '_check_tml_build_helper_converts_wsl_external_deps_for_windows_dotnet',
    '_check_tml_build_helper_converts_wsl_project_for_windows_dotnet',
    '_check_tml_build_log_parser_extracts_roslyn_errors_and_warnings',
    '_check_tml_build_log_parser_handles_tml_client_log_prefixes_and_dedupes'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_csharp_compile_surface_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
