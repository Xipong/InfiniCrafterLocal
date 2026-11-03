#nullable enable
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using System;
using System.IO;
using System.Text;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Runtime;

// An owner-hit receipt, NOT a collision proof. The server chooses all actions and
// parameters from its own authored definition; the wire carries no buff/damage/force.
// NPC velocity has no owner-side vanilla sync equivalent to AddBuff/ApplyDamageToNPC.
internal static class RuntimeHitPullBridge
{
    private const byte Version = 4;
    private const byte ProjectileSource = 1;
    private const byte ItemSource = 2;
    private const int MaxClaimsPerTick = 32;
    private static uint _nextSequence;
    private static readonly Player?[] LastOwner = new Player?[Main.maxPlayers];
    private static readonly uint[] LastSequence = new uint[Main.maxPlayers];
    private static readonly ulong[] ClaimTick = new ulong[Main.maxPlayers];
    private static readonly Player?[] ClaimOwner = new Player?[Main.maxPlayers];
    private static readonly int[] ClaimCount = new int[Main.maxPlayers];
    private const int RecentItemSources = 8;
    private readonly record struct ItemActivation(Player Owner, int Slot, Item Host, Item Item,
        GeneratedItemData Data, RuntimeEntitySpec Entity, ulong Tick);
    private static readonly ItemActivation?[,] LastItem = new ItemActivation?[Main.maxPlayers, RecentItemSources];
    private static readonly int[] NextItem = new int[Main.maxPlayers];

    // Capture only server-visible selected generated items; a subsequent inventory/use-mode
    // packet may advance before the hit receipt. Contact bindings are checked at receipt.
    internal static void RememberItemActivation(Player owner)
    {
        if (Main.netMode != NetmodeID.Server || owner is null || !owner.active
            || owner.whoAmI < 0 || owner.whoAmI >= Main.maxPlayers
            || owner.selectedItem < 0 || owner.selectedItem >= owner.inventory.Length
            || owner.inventory[owner.selectedItem]?.ModItem is not GeneratedItem item
            || item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId) is not { } entity
            || !HasServerHitActions(entity, true)
            || (item.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse)?.UsePolicy.ContactDamage != true
                && item.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.AlternateUse)?.UsePolicy.ContactDamage != true)
            || !GeneratedItemRegistryService.IsCurrentWorldData(item.Data)) return;
        int player = owner.whoAmI;
        Item host = owner.inventory[owner.selectedItem];
        for (int i = 0; i < RecentItemSources; i++)
        {
            if (LastItem[player, i] is not { } previous
                || !ReferenceEquals(previous.Owner, owner) || previous.Slot != owner.selectedItem
                || !ReferenceEquals(previous.Host, host) || !ReferenceEquals(previous.Data, item.Data)
                || !ReferenceEquals(previous.Entity, entity)) continue;
            LastItem[player, i] = previous with { Tick = Main.GameUpdateCount };
            return;
        }
        int index = NextItem[player];
        NextItem[player] = (index + 1) % RecentItemSources;
        LastItem[player, index] = new ItemActivation(owner, owner.selectedItem, host,
            host.Clone(), item.Data, entity, Main.GameUpdateCount);
    }

    private static bool AdmitClaim(int sender, Player owner)
    {
        if (!ReferenceEquals(ClaimOwner[sender], owner) || ClaimTick[sender] != Main.GameUpdateCount)
        {
            ClaimOwner[sender] = owner;
            ClaimTick[sender] = Main.GameUpdateCount;
            ClaimCount[sender] = 0;
        }
        return ++ClaimCount[sender] <= MaxClaimsPerTick;
    }
    private readonly record struct RetiredProjectile(Projectile? Host, ModProjectile? Generation, int Identity, ulong Tick);
    private static readonly RetiredProjectile[] Retired = new RetiredProjectile[Main.maxProjectiles];

    internal static void RememberRetired(Projectile projectile)
    {
        if (Main.netMode != NetmodeID.Server || projectile is null
            || projectile.whoAmI < 0 || projectile.whoAmI >= Retired.Length
            || projectile.ModProjectile is not GeneratedProjectile generated
            || !generated.TryGetHitSource(out _, out _)) return;
        Retired[projectile.whoAmI] = new RetiredProjectile(projectile, generated, projectile.identity, Main.GameUpdateCount);
    }

    // The same bounded retirement fence also admits delayed owner VFX hit
    // claims. It never returns a recycled slot or an ambiguous identity.
    internal static Projectile? FindProjectile(int owner, int identity)
    {
        Projectile? match = null;
        for (int slot = 0; slot < Math.Min(Main.maxProjectiles, Main.projectile.Length); slot++)
        {
            Projectile? projectile = Main.projectile[slot];
            if (projectile is not { active: true } || projectile.owner != owner || projectile.identity != identity)
                continue;
            if (match is not null) return null; // ambiguous network identity, not a slot hint
            match = projectile;
        }
        for (int slot = 0; slot < Math.Min(Retired.Length, Main.projectile.Length); slot++)
        {
            RetiredProjectile retired = Retired[slot];
            Projectile? projectile = retired.Host;
            if (projectile is null || !ReferenceEquals(Main.projectile[slot], projectile)
                || projectile.active || projectile.owner != owner || projectile.identity != identity
                || retired.Identity != identity || !ReferenceEquals(retired.Generation, projectile.ModProjectile)
                || Main.GameUpdateCount < retired.Tick || Main.GameUpdateCount - retired.Tick > 60)
                continue;
            if (match is not null) return null;
            match = projectile;
        }
        return match;
    }

    private static bool HasServerHitActions(RuntimeEntitySpec entity, bool crit)
    {
        foreach (RuntimeEventActionSpec action in entity.ActionsFor(RuntimeEventKind.OnHit))
            if (IsServerHitAction(action)) return true;
        if (crit)
            foreach (RuntimeEventActionSpec action in entity.ActionsFor(RuntimeEventKind.OnCrit))
                if (IsServerHitAction(action)) return true;
        return false;
    }

    private static bool IsServerHitAction(RuntimeEventActionSpec action)
        => action.ActionCode == RuntimeEventActionCode.ApplyNpcEffect
            || action.ActionCode == RuntimeEventActionCode.Pull && action.Mode != "owner_to_target";

    // The owner rolls once at hit admission, BEFORE queuing or sending. The
    // receiver validates selected indices against its exact definition and never
    // rolls again. This is the existing bounded owner-hit claim, not collision proof.
    internal static ushort SelectNpcEffectMask(RuntimeEntitySpec entity, bool crit, Func<double>? random = null)
    {
        ushort mask = 0;
        for (int i = 0; i < Math.Min(entity.Events.Length, 16); i++)
        {
            RuntimeEventActionSpec action = entity.Events[i];
            if (action.ActionCode != RuntimeEventActionCode.ApplyNpcEffect || action.NpcEffect is not { HasEffect: true } effect
                || !(action.Event == RuntimeEventKind.OnHit || crit && action.Event == RuntimeEventKind.OnCrit)) continue;
            if (effect.Chance >= 1f || effect.Chance > 0f && (random?.Invoke() ?? Main.rand.NextDouble()) < effect.Chance)
                mask |= (ushort)(1 << i);
        }
        return mask;
    }

    private static bool ValidNpcEffectMask(RuntimeEntitySpec entity, bool crit, ushort mask)
    {
        for (int i = 0; i < 16; i++)
        {
            if ((mask & (1 << i)) == 0) continue;
            if (i >= entity.Events.Length) return false;
            RuntimeEventActionSpec action = entity.Events[i];
            if (action.ActionCode != RuntimeEventActionCode.ApplyNpcEffect || action.NpcEffect is not { HasEffect: true, Chance: > 0f }
                || !(action.Event == RuntimeEventKind.OnHit || crit && action.Event == RuntimeEventKind.OnCrit)) return false;
        }
        return true;
    }

    internal static bool TryWriteProjectileReceipt(BinaryWriter writer, Projectile source, NPC target, bool crit)
    {
        if (writer is null || source is null || target is not { active: true }
            || Main.netMode != NetmodeID.MultiplayerClient || source.owner != Main.myPlayer
            || source.whoAmI < 0 || source.whoAmI >= Main.maxProjectiles
            || source.ModProjectile is not GeneratedProjectile generated
            || !generated.TryGetHitSource(out GeneratedItemData data, out RuntimeEntitySpec entity)
            || !ValidIdentity(data.Id, entity.Id)
            || !HasServerHitActions(entity, crit)) return false;
        Write(writer, ProjectileSource, source.identity, target.whoAmI,
            RuntimeHitNpcGeneration.Get(target), 0, 0, crit, data.Id, entity.Id, SelectNpcEffectMask(entity, crit));
        return true;
    }

    internal static bool TryWriteItemReceipt(BinaryWriter writer, Player owner, GeneratedItem item, NPC target, bool crit)
    {
        if (writer is null || owner is null || item is null || target is not { active: true }
            || Main.netMode != NetmodeID.MultiplayerClient || owner.whoAmI != Main.myPlayer
            || owner.selectedItem < 0 || owner.selectedItem >= owner.inventory.Length
            || owner.HeldItem?.ModItem != item
            || item.Data.RuntimeProgram.BindingForInput(owner.altFunctionUse == 2
                ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse)?.UsePolicy.ContactDamage != true
            || item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId) is not { } entity
            || !ValidIdentity(item.Data.Id, entity.Id)
            || !HasServerHitActions(entity, crit)) return false;
        Write(writer, ItemSource, 0, target.whoAmI, RuntimeHitNpcGeneration.Get(target),
            (byte)owner.selectedItem, (byte)(owner.altFunctionUse == 2 ? 2 : 1), crit,
            item.Data.Id, entity.Id, SelectNpcEffectMask(entity, crit));
        return true;
    }

    private static bool ValidIdentity(string itemId, string entityId)
        => !string.IsNullOrEmpty(itemId) && Encoding.UTF8.GetByteCount(itemId) <= 96
            && !string.IsNullOrEmpty(entityId) && Encoding.UTF8.GetByteCount(entityId) <= 48;

    private static void WriteIdentity(BinaryWriter writer, string identity)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(identity);
        writer.Write((byte)bytes.Length);
        writer.Write(bytes);
    }

    private static string ReadIdentity(BinaryReader reader, int maxBytes)
    {
        int length = reader.ReadByte();
        if (length < 1 || length > maxBytes) throw new InvalidDataException("invalid hit identity length");
        byte[] bytes = reader.ReadBytes(length);
        if (bytes.Length != length) throw new EndOfStreamException();
        return new UTF8Encoding(false, true).GetString(bytes);
    }

    private static void Write(BinaryWriter writer, byte kind, int identity, int npc, uint npcGeneration,
        byte itemSlot, byte input, bool crit, string itemId, string entityId, ushort npcEffects)
    {
        writer.Write(Version);
        writer.Write(kind);
        writer.Write(identity);
        writer.Write((short)npc);
        writer.Write(npcGeneration);
        writer.Write(itemSlot);
        writer.Write(input);
        writer.Write(crit);
        writer.Write(++_nextSequence);
        WriteIdentity(writer, itemId);
        WriteIdentity(writer, entityId);
        writer.Write(npcEffects);
    }

    internal static void SendProjectileHit(Projectile source, NPC target, bool crit)
    {
        if (Main.netMode == NetmodeID.SinglePlayer && source.ModProjectile is GeneratedProjectile local
            && source.owner >= 0 && source.owner < Main.maxPlayers
            && local.TryGetHitSource(out GeneratedItemData localData, out RuntimeEntitySpec localEntity))
        {
            ApplyLocalEffects(localEntity, localData, Main.player[source.owner], source.GetSource_FromThis(), source.Center, target, crit);
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient || source.owner != Main.myPlayer
            || source.ModProjectile is not GeneratedProjectile generated
            || !generated.TryGetHitSource(out _, out RuntimeEntitySpec entity)
            || !HasServerHitActions(entity, crit)
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null) return;
        ModPacket packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedHitNpcPull);
        if (TryWriteProjectileReceipt(packet, source, target, crit)) packet.Send();
    }

    internal static void SendItemHit(Player owner, GeneratedItem item, NPC target, bool crit)
    {
        if (Main.netMode == NetmodeID.SinglePlayer
            && item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId) is { } localEntity)
        {
            ApplyLocalEffects(localEntity, item.Data, owner, owner.GetSource_ItemUse(item.Item), target.Center, target, crit);
            return;
        }
        if (Main.netMode != NetmodeID.MultiplayerClient || owner.whoAmI != Main.myPlayer
            || item.Data.RuntimeProgram.TryGetEntity(item.Data.RuntimeProgram.ItemEntityId) is not { } entity
            || !HasServerHitActions(entity, crit)
            || global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance is null) return;
        ModPacket packet = global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance.GetPacket();
        packet.Write(global::InfiniCrafterLocal.Common.InfiniNetPacketIds.GeneratedHitNpcPull);
        if (TryWriteItemReceipt(packet, owner, item, target, crit)) packet.Send();
    }

    internal static void HandlePacket(BinaryReader reader, int whoAmI)
    {
        if (reader is null || Main.netMode != NetmodeID.Server || whoAmI < 0 || whoAmI >= Main.maxPlayers)
            return;
        byte version, kind, itemSlot, input; short npcSlot; int identity; uint npcGeneration; bool crit; uint sequence;
        string itemId, entityId; ushort npcEffects;
        try
        {
            version = reader.ReadByte(); kind = reader.ReadByte();
            identity = reader.ReadInt32(); npcSlot = reader.ReadInt16();
            npcGeneration = reader.ReadUInt32(); itemSlot = reader.ReadByte(); input = reader.ReadByte();
            crit = reader.ReadBoolean(); sequence = reader.ReadUInt32();
            itemId = ReadIdentity(reader, 96); entityId = ReadIdentity(reader, 48);
            npcEffects = reader.ReadUInt16();
        }
        catch (Exception error) when (error is EndOfStreamException or InvalidDataException or DecoderFallbackException) { return; }
        if (version != Version || (kind != ProjectileSource && kind != ItemSource)
            || npcSlot < 0 || npcSlot >= Main.maxNPCs || sequence == 0 || npcGeneration == 0) return;
        Player owner = Main.player[whoAmI];
        if (owner is null || !owner.active || owner.whoAmI != whoAmI
            || Main.npc[npcSlot] is not { active: true } target
            || RuntimeHitNpcGeneration.Get(target) != npcGeneration
            || !AdmitClaim(whoAmI, owner)) return;
        RuntimeEntitySpec entity; GeneratedItemData data; Terraria.DataStructures.IEntitySource source;
        // Item receipts retain their existing target-centered origin. Projectile
        // receipts use only the server-resolved source, never client coordinates.
        var sourceCenter = target.Center;
        if (kind == ProjectileSource)
        {
            if (itemSlot != 0 || input != 0) return;
            Projectile? projectile = FindProjectile(whoAmI, identity);
            if (projectile?.ModProjectile is not GeneratedProjectile generated
                || !generated.TryGetHitSource(out data, out entity)) return;
            source = projectile.GetSource_FromThis();
            sourceCenter = projectile.Center;
        }
        else
        {
            if (identity != 0 || input is not (1 or 2) || itemSlot >= owner.inventory.Length)
                return;
            ItemActivation? matched = null;
            for (int i = 0; i < RecentItemSources; i++)
            {
                if (LastItem[whoAmI, i] is not { } candidate
                    || !ReferenceEquals(candidate.Owner, owner) || candidate.Slot != itemSlot
                    || Main.GameUpdateCount < candidate.Tick || Main.GameUpdateCount - candidate.Tick > 60
                    || !string.Equals(candidate.Data.Id, itemId, StringComparison.Ordinal)
                    || !string.Equals(candidate.Entity.Id, entityId, StringComparison.Ordinal)) continue;
                if (matched is not null) return; // same slot/identity, ambiguous item incarnation
                matched = candidate;
            }
            if (matched is not { } activation
                || activation.Data.RuntimeProgram.BindingForInput(input == 2
                    ? RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse)?.UsePolicy.ContactDamage != true)
                return;
            data = activation.Data; entity = activation.Entity;
            source = owner.GetSource_ItemUse(activation.Item);
        }
        if (!string.Equals(data.Id, itemId, StringComparison.Ordinal)
            || !string.Equals(entity.Id, entityId, StringComparison.Ordinal)
            || !GeneratedItemRegistryService.IsCurrentWorldData(data)
            || !HasServerHitActions(entity, crit) || !ValidNpcEffectMask(entity, crit, npcEffects)) return;
        if (ReferenceEquals(LastOwner[whoAmI], owner) && sequence <= LastSequence[whoAmI]) return;
        LastOwner[whoAmI] = owner;
        LastSequence[whoAmI] = sequence;
        Apply(entity, data, owner, source, sourceCenter, target, RuntimeEventKind.OnHit, npcEffects);
        if (crit) Apply(entity, data, owner, source, sourceCenter, target, RuntimeEventKind.OnCrit, npcEffects);
    }

    private static void ApplyLocalEffects(RuntimeEntitySpec entity, GeneratedItemData data, Player owner,
        Terraria.DataStructures.IEntitySource source, Microsoft.Xna.Framework.Vector2 center, NPC target, bool crit)
    {
        if (owner is not { active: true } || target is not { active: true }) return;
        ushort mask = SelectNpcEffectMask(entity, crit);
        Apply(entity, data, owner, source, center, target, RuntimeEventKind.OnHit, mask, effectsOnly: true);
        if (crit) Apply(entity, data, owner, source, center, target, RuntimeEventKind.OnCrit, mask, effectsOnly: true);
    }

    private static void Apply(RuntimeEntitySpec entity, GeneratedItemData data, Player owner,
        Terraria.DataStructures.IEntitySource source, Microsoft.Xna.Framework.Vector2 sourceCenter, NPC target, string eventName, ushort npcEffects, bool effectsOnly = false)
    {
        for (int i = 0; i < entity.Events.Length; i++)
        {
            RuntimeEventActionSpec action = entity.Events[i];
            if (action.Event != eventName) continue;
            if (action.ActionCode == RuntimeEventActionCode.ApplyNpcEffect)
            {
                if (i >= 16 || (npcEffects & (1 << i)) == 0) continue;
            }
            else if (effectsOnly || action.ActionCode != RuntimeEventActionCode.Pull || action.Mode == "owner_to_target") continue;
            var budget = new RuntimeSpawnBudget(0);
            var eventPosition = RuntimeProgramExecutor.ProjectileEventPosition(action, sourceCenter, target);
            if (action.DelayTicks > 0)
                RuntimeDelayedActionScheduler.TrySchedule(data, entity, action, owner, source,
                    eventPosition, Microsoft.Xna.Framework.Vector2.Zero, target, 0, 0, budget,
                    ownerHitReceipt: true);
            else
                RuntimeProgramExecutor.ExecuteAction(data, entity, action, owner, source,
                    eventPosition, Microsoft.Xna.Framework.Vector2.Zero, target, 0, 0, budget);
        }
    }

    internal static void Clear()
    {
        Array.Clear(LastOwner); Array.Clear(LastSequence); Array.Clear(Retired);
        Array.Clear(LastItem); Array.Clear(NextItem); Array.Clear(ClaimTick);
        Array.Clear(ClaimOwner); Array.Clear(ClaimCount);
        RuntimeHitNpcGeneration.Clear(); _nextSequence = 0;
    }
}

public sealed class RuntimeHitPullBridgeSystem : ModSystem
{
    public override void PostUpdatePlayers()
    {
        if (Main.netMode != NetmodeID.Server) return;
        for (int i = 0; i < Main.maxPlayers; i++)
            if (Main.player[i] is { active: true } owner)
                RuntimeHitPullBridge.RememberItemActivation(owner);
    }

    public override void OnWorldUnload() => RuntimeHitPullBridge.Clear();
    public override void Unload() => RuntimeHitPullBridge.Clear();
}
