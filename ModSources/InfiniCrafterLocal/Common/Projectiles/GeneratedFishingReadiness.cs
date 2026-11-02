#nullable enable
using System;
using System.IO;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;
using Snapshot = InfiniCrafterLocal.Content.Items.GeneratedItem.NativeUseSnapshot;

namespace InfiniCrafterLocal.Common.Projectiles;

// Only a source-associated native bobber replica may wait for its accepted item
// definition. Vanilla fishing AI still owns bait, bite, catch, cancellation and life.
public sealed class GeneratedFishingReadiness : GlobalProjectile
{
    internal const ulong DefinitionWaitTicks = 5 * 60; // existing registry catch-up window
    public override bool InstancePerEntity => true;
    public override bool AppliesToEntity(Projectile entity, bool lateInstantiation)
        => entity.type == ProjectileID.BobberWooden;

    private Snapshot? _source;
    private string _itemId = "";
    private bool _invalid, _ready;
    private ulong? _waitStarted;

    public override void OnSpawn(Projectile projectile, IEntitySource source)
    {
        if (projectile.type != ProjectileID.BobberWooden || Main.netMode != NetmodeID.MultiplayerClient || projectile.owner != Main.myPlayer
            || source is not EntitySource_ItemUse use || use.Player.whoAmI != projectile.owner
            || use.Item.ModItem is not GeneratedItem item || !item.HasResolvedNativeUseDefinition
            || item.NativeUseProjection is not Snapshot witness || !witness.Valid
            || witness.Owner != projectile.owner || witness.Token != item.PresentationToken
            || witness.Definition != item.NativeUseDefinition
            || item.Data.RuntimeProgram.BindingForInput(witness.InputName)?.UsePolicy.Action.Kind
                != RuntimeBindingAction.NativeFishing) return;
        if (string.IsNullOrEmpty(item.Data.Id) || item.Data.Id.Length > 96) return;
        _source = witness; _itemId = item.Data.Id;
    }

    public override void SendExtraAI(Projectile projectile, BitWriter bitWriter, BinaryWriter writer)
    {
        bitWriter.WriteBit(_source.HasValue || _invalid);
        if (_source is not Snapshot value) {
            if (_invalid) writer.Write((byte)0); // invalid association remains invalid through relay
            return;
        }
        writer.Write((byte)1);
        byte[] id = Encoding.UTF8.GetBytes(_itemId); writer.Write((ushort)id.Length); writer.Write(id);
        writer.Write(value.Slot); writer.Write(value.Token); writer.Write(value.Revision); writer.Write(value.Input);
        writer.Write(Convert.FromHexString(value.Definition));
    }

    public override void ReceiveExtraAI(Projectile projectile, BitReader bitReader, BinaryReader reader)
    {
        try {
            if (!bitReader.ReadBit()) return; // ordinary vanilla bobber; never adopt current held identity
            if (reader.ReadByte() != 1) throw new InvalidDataException("unsupported fishing source witness");
            int idLength = reader.ReadUInt16();
            if (idLength is < 1 or > 384) throw new InvalidDataException("invalid fishing source item identity");
            byte[] idBytes = reader.ReadBytes(idLength);
            if (idBytes.Length != idLength) throw new EndOfStreamException();
            string itemId = new UTF8Encoding(false, true).GetString(idBytes);
            if (itemId.Length > 96 || (_source.HasValue && itemId != _itemId)) throw new InvalidDataException("inconsistent fishing source item identity");
            byte slot = reader.ReadByte(); long token = reader.ReadInt64(); ulong revision = reader.ReadUInt64(); byte input = reader.ReadByte();
            byte[] hash = reader.ReadBytes(32);
            if (hash.Length != 32) throw new EndOfStreamException();
            var value = new Snapshot((byte)projectile.owner, slot, token, revision, input, Convert.ToHexString(hash).ToLowerInvariant());
            if (!value.Valid || (_source.HasValue && _source.Value != value)) throw new InvalidDataException("inconsistent fishing source witness");
            _source = value; _itemId = itemId; // repeated packets do not reset readiness or its deadline
        }
        catch (InvalidDataException) { _invalid = true; }
        catch (IOException) { _invalid = true; }
        catch (DecoderFallbackException) { _invalid = true; }
    }

    public override bool PreAI(Projectile projectile) => ReadyForNativeUpdate(projectile);
    public override bool ShouldUpdatePosition(Projectile projectile) => ReadyForNativeUpdate(projectile);

    private bool ReadyForNativeUpdate(Projectile projectile)
    {
        if (!projectile.active) return false;
        if (Main.netMode == NetmodeID.SinglePlayer || projectile.owner == Main.myPlayer) return true;
        if (_invalid) return Retire(projectile);
        // Once hydrated, return ownership permanently to native cancellation/lifetime.
        if (_source is not Snapshot witness || _ready) return true;
        if (projectile.owner < 0 || projectile.owner >= Main.maxPlayers) return Retire(projectile);
        Player owner = Main.player[projectile.owner];
        if (owner is null || !owner.active || owner.dead || owner.selectedItem != witness.Slot
            || owner.HeldItem.ModItem is not GeneratedItem item || item.InvalidNativeUseProjection
            || item.Data.Id != _itemId || item.PresentationToken != witness.Token || item.NativeUseProjection != witness)
            return Retire(projectile);
        if (item.HasResolvedNativeUseDefinition) {
            if (item.NativeUseDefinition != witness.Definition
                || owner.GetModPlayer<InfiniCraftPlayer>().ResolveNativeUseProjection(item)?.UsePolicy.Action.Kind
                    != RuntimeBindingAction.NativeFishing) return Retire(projectile);
            _ready = true;
            return true;
        }
        ulong now = Main.GameUpdateCount;
        _waitStarted ??= now;
        if (now < _waitStarted.Value || now - _waitStarted.Value >= DefinitionWaitTicks) return Retire(projectile);
        // Existing item hydration requests/retries run from PreItemCheck/HoldItem.
        // Do not refresh timeLeft, spawn a replacement, consume resources or replay use.
        return false;
    }

    private static bool Retire(Projectile projectile)
    {
        projectile.Kill();
        return false;
    }
}
