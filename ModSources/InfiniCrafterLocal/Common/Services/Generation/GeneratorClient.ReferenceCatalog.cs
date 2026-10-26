#nullable enable
using System;
using System.Text.Json.Nodes;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Identity lookup only. ModBuff.SetupContent registers FullName in this same
    // native dictionary; reading it does not execute a buff or an item hook.
    private static JsonObject? CaptureLoadedBuffIdentities(int maxEntries = 2048)
    {
        if (maxEntries < 1 || maxEntries > 2048)
            throw new ArgumentOutOfRangeException(nameof(maxEntries));
        try
        {
            int count = BuffLoader.BuffCount;
            var entries = new JsonArray();
            bool complete = count <= 65536;
            for (int id = 1; id < count && id <= 65535; id++)
            {
                if (entries.Count == maxEntries)
                {
                    complete = false;
                    break;
                }
                if (!BuffID.Search.ContainsId(id))
                {
                    complete = false;
                    continue;
                }
                string name = BuffID.Search.GetName(id);
                string fullName = id < BuffID.Count ? "Terraria/" + name : name;
                if (string.IsNullOrEmpty(name) || fullName.Length > 256)
                {
                    complete = false;
                    continue;
                }
                entries.Add(new JsonObject { ["id"] = id, ["fullName"] = fullName });
            }
            return entries.Count == 0 ? null : new JsonObject
            {
                ["source"] = "native_loaded_buff_registry",
                ["scope"] = "Current registered identities only; not parent behavior or an immunity/effect guarantee.",
                ["complete"] = complete,
                ["entries"] = entries,
            };
        }
        catch
        {
            // Old/unloaded registry stays unknown, not an invented empty catalog.
            return null;
        }
    }
}
