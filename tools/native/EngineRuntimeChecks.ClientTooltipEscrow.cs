#nullable enable
using System;
using System.IO;
using System.Reflection;
using System.Linq;
using System.Text;
using System.Text.Json;
using InfiniCrafterLocal.Common.Config;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.Localization;
using Terraria.ModLoader;
using Terraria.UI;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Mono.Cecil.Cil;

internal static partial class EngineRuntimeChecks
{
    // Only external task/socket and server policy boundaries are intercepted;
    // packet decode, escrow, identity validation and actual Prepare remain native.
    private static void ClientTooltipServerCraftEscrowEndToEnd()
    {
        var genProperty = typeof(InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Generator")!;
        object? previousGenerator = genProperty.GetValue(null);
        var oldLanguage = LanguageManager.Instance;
        var oldPrefixes=(LocalizedText[])Lang.prefix.Clone();
        var oldTips=(LocalizedText[])Lang.tip.Clone();
        var tooltipField = typeof(Lang).GetField("_itemTooltipCache", RootPrivate)!;
        var cache = (ItemTooltip[])tooltipField.GetValue(null)!;
        var oldTooltipA = cache[ItemID.CopperShortsword];
        var oldTooltipB = cache[ItemID.Wood];
        bool trust = false; int started = 0;
        var enabledGetter = typeof(InfiniParentTooltipServerConfig).GetProperty("Enabled", RootPrivate)!.GetMethod!;
        var startTask = typeof(InfiniCraftPlayer).GetMethod("StartGenerationTask", PersistenceInstance)!;
        using var policyHook = new ILHook(enabledGetter, il => {
            var c = new ILCursor(il); c.EmitDelegate<Func<bool>>(() => trust); c.Emit(OpCodes.Ret);
        });
        using var noHttp = new ILHook(startTask, il => {
            var c = new ILCursor(il); c.EmitDelegate<Action>(() => started++); c.Emit(OpCodes.Ret);
        });
        using var peers = new ReviewPeers(); peers.Mode(NetmodeID.Server, 255);
        var world = new GeneratedStationEscrowStateSystem();
        try
        {
            var manager = (LanguageManager)Activator.CreateInstance(typeof(LanguageManager), true)!;
            typeof(LanguageManager).GetProperty("ActiveCulture")!.SetValue(manager, GameCulture.FromName("en-US"));
            LanguageManager.Instance = manager;
            for(int i=0;i<Lang.prefix.Length;i++) Lang.prefix[i] ??= LocalizedText.Empty;
            for(int i=0;i<Lang.tip.Length;i++) Lang.tip[i] ??= LocalizedText.Empty;
            ItemTooltip MakeTooltip(string text) => ItemTooltip.FromLocalization(
                (LocalizedText)Activator.CreateInstance(typeof(LocalizedText), RootPrivate, null,
                    new object[] { "probe." + text, text }, null)!);
            cache[ItemID.CopperShortsword] = MakeTooltip("server-A");
            cache[ItemID.Wood] = MakeTooltip("server-B");
            genProperty.SetValue(null, new GeneratorClient());
            foreach (var scenario in new[] { (allow:false, generated:false, clientCapture:false), (allow:true, generated:false, clientCapture:false), (allow:true, generated:true, clientCapture:false), (allow:true, generated:false, clientCapture:true) })
            {
                bool allow=scenario.allow, generated=scenario.generated, clientCapture=scenario.clientCapture;
                trust = allow; started = 0; world.ClearWorld();
                using (var init = new BinaryWriter(new MemoryStream())) world.NetSend(init);
                string scope = GeneratedStationEscrowStateSystem.AuthorityScope;
                string token = new string(generated ? 'e' : allow ? 'b' : 'a', 32);
                string request = new string(allow ? 'd' : 'c', 32);
                WithPlayer((player, owner) => {
                    EscrowBind(player, owner, token, 0);
                    owner.InputA = new Item(ItemID.CopperShortsword, 1);
                    owner.InputB = new Item(ItemID.Wood, 1);
                    string generatedId="";
                    if (generated) {
                        var definition = GeneratedItemData.Placeholder(); definition.Id="g_tooltip_probe";
                        peers.Register(definition);
                        AttachItem(new GeneratedItem(), owner.InputA, definition);
                        definition.ApplyToItem(owner.InputA);
                        generatedId=definition.Id;
                    }
                    ClientTooltipObservation? captured = null;
                    if (clientCapture) {
                        var mod = new TooltipProbeItem { State=7 };
                        typeof(ModType<Item>).GetProperty("Entity", RootPrivate)!.SetValue(mod, owner.InputA);
                        typeof(Item).GetProperty("ModItem", RootPrivate)!.SetValue(owner.InputA, mod);
                        owner.InputA.RebuildTooltip();
                        Terraria.Main.dedServ=false; Terraria.Main.netMode=NetmodeID.MultiplayerClient; Terraria.Main.myPlayer=0;
                        captured=GeneratorClient.CaptureClientTooltip(owner.InputA, player);
                        Equal(true, captured is not null, "actual local ModItem capture succeeds");
                        Equal("item-7,added-7", string.Join(",", captured!.Lines), "actual hook produced dynamic lines");
                        Terraria.Main.netMode=NetmodeID.Server; Terraria.Main.myPlayer=255; Terraria.Main.dedServ=true;
                    }
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(token, owner);
                    byte[] Packet(string req, int aType, string line)
                    {
                        using var bytes = new MemoryStream();
                        using (var writer = new BinaryWriter(bytes, Encoding.UTF8, true)) {
                            writer.Write(3); writer.Write(scope); writer.Write(token); writer.Write(req); writer.Write((byte)0);
                            void Ref(int type) { writer.Write(type); writer.Write(0); writer.Write(1); writer.Write(type == ItemID.CopperShortsword ? generatedId : ""); writer.Write(""); }
                            Ref(aType); Ref(ItemID.Wood);
                            ClientTooltipWire.Write(writer, clientCapture && line == "client-A" ? captured : new ClientTooltipObservation(new[] { line }, "ru-RU"));
                            ClientTooltipWire.Write(writer, new ClientTooltipObservation(new[] { "client-B" }, "ru-RU"));
                        }
                        return bytes.ToArray();
                    }
                    void Receive(byte[] bytes, int sender=0) => InfiniCraftPlayer.HandleRequestServerCraftPacket(new BinaryReader(new MemoryStream(bytes)), sender);
                    // Correct owner but wrong item reference cannot inject content or reserve inputs.
                    string wrong = new string('e', 32);
                    Receive(Packet(wrong, ItemID.DirtBlock, "spoof"));
                    Equal(0, started, "spoofed parent does not launch");
                    Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, wrong), "spoof does not reserve");
                    Equal(ItemID.CopperShortsword, owner.InputA.type, "spoof keeps server input A");
                    Equal(ItemID.Wood, owner.InputB.type, "spoof keeps server input B");
                    WithPlayer((foreign, foreignOwner) => {
                        foreignOwner.Initialize(); foreign.whoAmI=1; foreign.active=true; Terraria.Main.player[1]=foreign;
                        Receive(Packet(new string('f',32), ItemID.CopperShortsword, "foreign"), 1);
                        Equal(0, started, "foreign live owner does not launch");
                    });
                    Receive(Packet(request, ItemID.CopperShortsword, "client-A"));
                    Equal(1, started, "admitted craft starts exactly once");
                    var prepared = (GeneratorClient.PreparedGenerationRequest)typeof(InfiniCraftPlayer)
                        .GetField("_request", PersistenceInstance)!.GetValue(owner)!;
                    string frozen = prepared.PayloadJson;
                    using (var document = JsonDocument.Parse(frozen)) {
                        var a = document.RootElement.GetProperty("itemA"); var b = document.RootElement.GetProperty("itemB");
                        if (!generated) Equal(new Item(ItemID.CopperShortsword).damage, a.GetProperty("damage").GetInt32(), "server native damage retained");
                        Equal(ItemID.CopperShortsword, a.GetProperty("id").GetInt32(), "server parent A identity retained");
                        Equal(ItemID.Wood, b.GetProperty("id").GetInt32(), "server parent B identity retained");
                        if (generated) {
                            Equal(0, a.GetProperty("tooltipLines").GetArrayLength(), "generated parents reject client override");
                            Equal(JsonValueKind.Null, a.GetProperty("tooltipSource").ValueKind, "generated tooltip has no false provenance");
                            Equal(generatedId, a.GetProperty("generatedData").GetProperty("id").GetString()!, "generated definition retained");
                        }
                        else Equal(clientCapture ? "item-7" : allow ? "client-A" : "server-A", a.GetProperty("tooltipLines")[0].GetString()!, "A scope-selected observation");
                        Equal(allow ? "client-B" : "server-B", b.GetProperty("tooltipLines")[0].GetString()!, "B scope-selected observation");
                        if (clientCapture) {
                            Equal("item-7,added-7", string.Join(",", a.GetProperty("tooltipLines").EnumerateArray().Select(x => x.GetString())), "all local ModItem lines survive wire and escrow");
                            Equal("en-US", a.GetProperty("tooltipSource").GetProperty("language").GetString()!, "actual capture locale survives wire");
                        }
                        if (!generated) {
                            Equal(allow ? "client_reported" : "Lang.GetTooltip", a.GetProperty("tooltipSource").GetProperty("source").GetString()!, "explicit observation source");
                            if (allow) Equal(false, a.GetProperty("tooltipSource").GetProperty("verified").GetBoolean(), "client observation is not verified");
                        }
                    }
                    Receive(Packet(request, ItemID.CopperShortsword, "changed replay"));
                    Equal(1, started, "pending replay does not start another generator");
                    Equal(frozen, prepared.PayloadJson, "pending replay cannot mutate frozen parent context");
                });
            }
        }
        finally {
            world.ClearWorld(); cache[ItemID.CopperShortsword]=oldTooltipA; cache[ItemID.Wood]=oldTooltipB;
            Array.Copy(oldPrefixes, Lang.prefix, oldPrefixes.Length); Array.Copy(oldTips, Lang.tip, oldTips.Length);
            LanguageManager.Instance=oldLanguage; genProperty.SetValue(null, previousGenerator);
        }
    }
}
