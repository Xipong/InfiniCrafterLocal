using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void PlacementReturnFullPoolKeepsDurableOwnerWithoutAllocation()
    {
        WithGeneratedPrefixScope(() => WithPersistenceTilemap((_, ledger) =>
        {
            using var serializer = WithPersistenceBoolSerializer();
            Item[] oldItems = Terraria.Main.item;
            int[] oldTimers = Terraria.Main.timeItemSlotCannotBeReusedFor;
            bool oldGen = WorldGen.gen;
            try
            {
                WorldGen.gen = false;
                Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1)
                    .Select(i => new Item(ItemID.Wood, 3) { active = i < Terraria.Main.maxItems,
                        timeSinceItemSpawned = i == 7 ? 999 : 1 }).ToArray();
                Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
                Item[] before = (Item[])Terraria.Main.item.Clone();
                var picker = typeof(Item).GetMethod("PickAnItemSlotToSpawnItemOn", PersistenceStatic)!;
                Equal(7, (int)picker.Invoke(null, new object[] { false, Terraria.Main.maxItems })!,
                    "real native full-pool allocator selects an occupied older drop");

                // Observe the unchanged canonical NewItem call without fabricating
                // a successful mod/world spawn. A scoped throw stops only that boundary.
                int allocations = 0;
                var core = typeof(GeneratedPlacementLedgerSystem).GetMethod("TrySpawnPendingReturnCore", PersistenceStatic)!;
                using var observer = new ILHook(core, il =>
                {
                    var site = il.Body.Instructions.Single(i => i.OpCode == OpCodes.Call
                        && i.Operand is Mono.Cecil.MethodReference m && m.DeclaringType.FullName == "Terraria.Item"
                        && m.Name == "NewItem");
                    new ILCursor(il) { Index = il.Body.Instructions.IndexOf(site) }.EmitDelegate<Action>(() =>
                    {
                        allocations++;
                        throw new InvalidOperationException("observed unchanged native return-allocation boundary");
                    });
                });
                var data = PlacementPrefixData(); string definition = data.ToNetworkJson();
                var prefix = new TagCompound { ["infiniNativePrefix"] = (int)PrefixID.Legendary };
                var group = new TagCompound {
                    ["groupId"] = new string('a', 32), ["generatedItemId"] = data.Id,
                    ["definitionJson"] = definition, ["nativePrefix"] = prefix,
                    ["cells"] = new List<TagCompound> { new() { ["layer"] = 2, ["x"] = 40, ["y"] = 40 } },
                };
                ledger.LoadWorldData(new TagCompound { ["infiniGeneratedPlacementLedgerV2"] = new List<TagCompound> { group } });
                Equal(true, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Wall, 40, 40), "break transfers accepted material ownership");
                Equal(0, allocations, "full pool refuses BEFORE NewItem can replace an occupied drop");
                Equal(false, GeneratedPlacementLedgerSystem.TryQueueReturn(GeneratedPlacementLayer.Wall, 40, 40), "same break cannot queue a second owner");
                void Pending(string reason)
                {
                    var save = new TagCompound(); ledger.SaveWorldData(save);
                    Equal(0, save.GetList<TagCompound>("infiniGeneratedPlacementLedgerV2").Count, reason + " placement retired");
                    var claim = save.GetList<TagCompound>("infiniGeneratedPlacementReturnsV2").Single();
                    Equal(group.GetString("groupId"), claim.GetString("groupId"), reason + " exact owner");
                    Equal(data.Id, claim.GetString("generatedItemId"), reason + " exact item identity");
                    Equal(definition, claim.GetString("definitionJson"), reason + " exact authoritative definition");
                    Equal((int)PrefixID.Legendary, claim.GetCompound("nativePrefix").GetInt("infiniNativePrefix"), reason + " prefix retained");
                    Equal(0, save.GetList<TagCompound>("infiniGeneratedPlacementReturnQuarantineV1").Count, reason + " pressure never quarantines");
                    ledger.LoadWorldData(PersistenceNbtRoundtrip(save));
                }
                for (int retry = 0; retry < 3; retry++) { ledger.PostUpdateWorld(); Pending("full retry/reload " + retry); }
                Equal(0, allocations, "retries never call replacement allocator");
                Equal(true, Terraria.Main.item.Select((item, i) => ReferenceEquals(item, before[i])
                    && item.stack == 3 && item.active == (i < Terraria.Main.maxItems)).All(v => v), "all occupied drops and dummy survive unchanged");

                Terraria.Main.item[2].active = false;
                Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 60;
                ledger.PostUpdateWorld(); Pending("cooling slot");
                Equal(0, allocations, "inactive cooling slot is not reusable capacity");
                Terraria.Main.timeItemSlotCannotBeReusedFor[2] = -1;
                ledger.PostUpdateWorld(); Pending("nonzero native timer");
                Equal(0, allocations, "native allocator requires exactly zero reuse timer");
                Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 0;
                Equal(2, (int)picker.Invoke(null, new object[] { false, Terraria.Main.maxItems })!, "real allocator chooses released inactive slot");
                Terraria.Main.netMode = NetmodeID.MultiplayerClient;
                ledger.PostUpdateWorld();
                Equal(0, allocations, "client mirror cannot deliver authoritative material");
                Terraria.Main.netMode = NetmodeID.Server;
                ledger.PostUpdateWorld();
                Equal(1, allocations, "server retry reaches unchanged native allocator once capacity returns");
                Pending("observed boundary interruption");
                Terraria.Main.netMode = NetmodeID.SinglePlayer;
                ledger.PostUpdateWorld();
                Equal(2, allocations, "single-player authority can retry same retained claim");
                Pending("single-player boundary interruption");
            }
            finally { Terraria.Main.item = oldItems; Terraria.Main.timeItemSlotCannotBeReusedFor = oldTimers; WorldGen.gen = oldGen; }
        }));
    }
}
