#nullable enable
using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    internal static int NativeUseInventorySlotCount => PlayerItemSlotID.InventoryMouseItem - PlayerItemSlotID.Inventory0 + 1;

    // This is a selected native-field projection, never an activation/payment receipt.
    internal readonly record struct NativeUseSnapshot(byte Owner, byte Slot, long Token,
        ulong Revision, byte Input, string Definition)
    {
        internal string InputName => Input == 0 ? RuntimeInputKind.PrimaryUse : RuntimeInputKind.AlternateUse;
        internal bool Valid => Owner < Main.maxPlayers && Slot < NativeUseInventorySlotCount && Token > 0 && Revision > 0
            && Input <= 1 && Definition.Length == 64;
    }

    private NativeUseSnapshot? _nativeUseSnapshot;
    private bool _invalidNativeUseSnapshot;
    private GeneratedItemData? _nativeUseDefinitionData;
    private string _nativeUseDefinition = "";
    internal NativeUseSnapshot? NativeUseProjection => _nativeUseSnapshot;
    internal bool InvalidNativeUseProjection => _invalidNativeUseSnapshot;
    internal bool UsesNativeInputProjection => _nativeUseSnapshot.HasValue || _invalidNativeUseSnapshot
        || Data.RuntimeProgram.BindingForInput(RuntimeInputKind.AlternateUse) is not null
        || Data.RuntimeProgram.Bindings.Any(binding => binding.UsePolicy.Action.Kind == RuntimeBindingAction.NativeFishing);
    internal string NativeUseDefinition
    {
        get {
            if (!ReferenceEquals(_nativeUseDefinitionData, Data)) {
                _nativeUseDefinition = GeneratedItemRegistryService.DefinitionIdentity(Data);
                _nativeUseDefinitionData = Data;
            }
            return _nativeUseDefinition;
        }
    }

    internal bool HasResolvedNativeUseDefinition => Data is not null && Data.Id != "placeholder"
        && !GeneratedItemData.IsPlayerSaveReferenceOnly(Data);

    internal void SetNativeUseProjection(NativeUseSnapshot snapshot)
    {
        _nativeUseSnapshot = snapshot;
        _invalidNativeUseSnapshot = false;
    }

    internal void ApplySynchronizedUseProjection(RuntimeBindingSpec binding)
        => ApplyActiveUseProjection(binding);

    private void WriteNativeUseSnapshot(BinaryWriter writer)
    {
        writer.Write(_nativeUseSnapshot.HasValue);
        if (_nativeUseSnapshot is not NativeUseSnapshot value) return;
        writer.Write(value.Owner); writer.Write(value.Slot); writer.Write(value.Revision); writer.Write(value.Input);
        writer.Write(Convert.FromHexString(value.Definition));
    }

    private NativeUseSnapshot? ReadNativeUseSnapshot(BinaryReader reader, long token)
    {
        if (!reader.ReadBoolean()) throw new InvalidDataException("missing native use projection snapshot");
        byte owner = reader.ReadByte(), slot = reader.ReadByte();
        ulong revision = reader.ReadUInt64(); byte input = reader.ReadByte();
        byte[] hash = reader.ReadBytes(32);
        if (hash.Length != 32) throw new EndOfStreamException("incomplete native use definition identity");
        var value = new NativeUseSnapshot(owner, slot, token, revision, input, Convert.ToHexString(hash).ToLowerInvariant());
        if (!value.Valid) throw new InvalidDataException("invalid native use projection snapshot");
        return value;
    }
}
