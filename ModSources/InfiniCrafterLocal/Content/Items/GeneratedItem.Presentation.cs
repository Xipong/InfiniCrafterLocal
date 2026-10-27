#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
namespace InfiniCrafterLocal.Content.Items;
public partial class GeneratedItem
{
    private static long _nextItemPresentationToken;
    private long _itemPresentationToken;
    // Retained v6 capability is independent of asynchronously hydrated slots.
    private bool _hasMaterialTransportIdentity;
    private bool HasMaterialTransportIdentity=>HasMaterialVfx||_hasMaterialTransportIdentity
        ||HasItemEventVfx;
    internal bool HasItemEventVfx=>Array.Exists(Data.VfxManifest.Slots,s=>s.PlacementBindingId is null
        &&s.EntityId==Data.RuntimeProgram.ItemEntityId&&s.Event!=RuntimeEventKind.Periodic);
    private object _itemPresentationGeneration=new();
    internal object PresentationGeneration=>_itemPresentationGeneration;
    internal long PresentationToken {
        get {
            if(_itemPresentationToken==0){
                _nextItemPresentationToken++;if(_nextItemPresentationToken==0)_nextItemPresentationToken++;_itemPresentationToken=_nextItemPresentationToken;
                // A freshly minted token changes only ItemIO metadata. Mark the
                // native item dirty so tML's IsNetStateDifferent sends the v8
                // identity even when type, stack and prefix are unchanged.
                if(Terraria.Main.netMode==Terraria.ID.NetmodeID.MultiplayerClient) Item.NetStateChanged();
            }
            return _itemPresentationToken;
        }
    }
    internal bool HasMaterialVfx=>Array.Exists(Data.VfxManifest.Slots,s=>InfiniDetachedVfxSystem.HasOwnedVfx(s));
    private void ApplyPresentationToken(long token)
    {
        _hasMaterialTransportIdentity=token!=0;
        if(_itemPresentationToken==token)return;
        _itemPresentationToken=token;_itemPresentationGeneration=new object();
        if(token>_nextItemPresentationToken)_nextItemPresentationToken=token;
    }
}
