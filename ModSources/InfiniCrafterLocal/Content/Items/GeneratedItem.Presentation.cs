#nullable enable
using System;
using InfiniCrafterLocal.Common.VFX;
namespace InfiniCrafterLocal.Content.Items;
public partial class GeneratedItem
{
    private static long _nextItemPresentationToken;
    private long _itemPresentationToken;
    // Retained v6 capability is independent of asynchronously hydrated slots.
    private bool _hasMaterialTransportIdentity;
    private bool HasMaterialTransportIdentity=>HasMaterialVfx||_hasMaterialTransportIdentity;
    private object _itemPresentationGeneration=new();
    internal object PresentationGeneration=>_itemPresentationGeneration;
    internal long PresentationToken {
        get {
            if(_itemPresentationToken==0){_nextItemPresentationToken++;if(_nextItemPresentationToken==0)_nextItemPresentationToken++;_itemPresentationToken=_nextItemPresentationToken;}
            return _itemPresentationToken;
        }
    }
    internal bool HasMaterialVfx=>Array.Exists(Data.VfxManifest.Slots,s=>s.Element is not null||s.Path is not null);
    private void ApplyPresentationToken(long token)
    {
        _hasMaterialTransportIdentity=token!=0;
        if(_itemPresentationToken==token)return;
        _itemPresentationToken=token;_itemPresentationGeneration=new object();
        if(token>_nextItemPresentationToken)_nextItemPresentationToken=token;
    }
}
