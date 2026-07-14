from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ModSources" / "InfiniCrafterLocal"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _contract_check_overhaul_qol_config_surface_exists():
    text = read("Common/Config/InfiniGameplayQolConfig.cs")
    for needle in [
        "EnableInventoryAssetPrefetch",
        "InventoryAssetPrefetchIntervalTicks",
        "ConfigScope.ClientSide",
    ]:
        assert needle in text
    for removed in ["EnableStationQuickFill", "QuickFillSkipsHotbar"]:
        assert removed not in text


def _contract_check_station_keeps_manual_clear_qol_without_quickfill_or_swap():
    ui = read("Common/UI/InfiniCraftStationUISystem.cs")
    player = read("Common/Players/InfiniCraftPlayer.cs")
    for needle in ["clearButton", "TryClearAllInputsToInventory", "TryClearInputToInventory", "Main.mouseRight"]:
        assert needle in ui or needle in player
    for removed in ["fillButton", "swapButton", "TryAutoFillStationInputs", "TrySwapStationInputs", "TryFillStationInputFromInventory", "QuickFillSkipsHotbar", "StationQuickFillEnabled"]:
        assert removed not in ui
        assert removed not in player


def _contract_check_inventory_asset_prefetch_is_bounded_and_optional():
    player = read("Common/Players/InfiniCraftPlayer.cs")
    for needle in [
        "TickGeneratedInventoryAssetPrefetch",
        "EnableInventoryAssetPrefetch",
        "InventoryAssetPrefetchIntervalTicks",
        "InventoryAssetPrefetchMaxItems",
        "GeneratedPrefetchCandidateItems",
        "GeneratedDataFromItem",
        "RegisterLocal(data, persist: true, ensureAssets: true)",
    ]:
        assert needle in player


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_overhaul_qol_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_overhaul_qol_config_surface_exists',
            '_contract_check_station_keeps_manual_clear_qol_without_quickfill_or_swap',
            '_contract_check_inventory_asset_prefetch_is_bounded_and_optional',
        ),
    )
