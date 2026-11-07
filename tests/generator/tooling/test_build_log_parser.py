from suite_paths import REPO_ROOT
from pathlib import Path
import sys

import pytest

ROOT = REPO_ROOT






@pytest.mark.parametrize("log,mod,code,line", [
    pytest.param((
        'mod/InfiniCrafterLocal/Content/Items/GeneratedItem.cs(12,34): error CS0246: Missing type\n'
        'mod/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs(99,5): warning CS0168: unused\n'
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
