using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using MonoMod.RuntimeDetour;
using Terraria;

// Observe the actual NPC.HitEffect call, including vanilla and ModNPC hooks.
// This never creates particles or changes the native hit/dust lifecycle.
internal sealed class WNativeHitFeedback : IDisposable
{
    delegate void HitEffectOriginal(NPC npc, NPC.HitInfo hit);
    delegate void HitEffectObserver(HitEffectOriginal orig, NPC npc, NPC.HitInfo hit);
    readonly Hook observer;

    public WNativeHitFeedback(Action<JsonObject> record)
    {
        MethodInfo method = typeof(NPC).GetMethod(nameof(NPC.HitEffect), new[] { typeof(NPC.HitInfo) })
            ?? throw new MissingMethodException("NPC.HitEffect(NPC.HitInfo)");
        observer = new Hook(method, (HitEffectObserver)((orig, npc, hit) => {
            bool[] before = Main.dust.Select(d => d is not null && d.active).ToArray();
            bool dedicated = Main.dedServ;
            orig(npc, hit);
            var created = new JsonArray();
            for (int i = 0; i < Main.dust.Length && i < before.Length; i++) {
                Dust dust = Main.dust[i];
                if (!before[i] && dust is not null && dust.active)
                    created.Add(new JsonObject { ["slot"] = i, ["type"] = dust.type });
            }
            record(new JsonObject { ["kind"] = "native_npc_hit_effect", ["npcId"] = npc.whoAmI,
                ["npcType"] = npc.type, ["damage"] = hit.Damage, ["critical"] = hit.Crit,
                ["dedServ"] = dedicated, ["newActiveDust"] = created,
                ["scope"] = "NPC.HitEffect including vanilla and NPCLoader hooks; newly active dust slots only" });
        }));
    }

    public void Dispose() => observer.Dispose();
}
