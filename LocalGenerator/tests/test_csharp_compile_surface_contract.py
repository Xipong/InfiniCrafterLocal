from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


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
