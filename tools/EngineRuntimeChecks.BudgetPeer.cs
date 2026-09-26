using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void PeerEventDoesNotOverwriteReceivedSpawnBudgetSnapshot()
    {
        int priorMode = Terraria.Main.netMode;
        int priorLocal = Terraria.Main.myPlayer;
        Player priorOwner = Terraria.Main.player[0];
        try
        {
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Terraria.Main.myPlayer = 1;
            Terraria.Main.player[0] = new Player { whoAmI = 0, active = true };
            var entity = Entity();
            entity.Id = "remote_budget_probe";
            entity.Kind = RuntimeEntityKind.FreeProjectile;
            entity.Events = new[] { new RuntimeEventActionSpec {
                Id = "early_kill_pull", Event = RuntimeEventKind.OnKill,
                ActionCode = RuntimeEventActionCode.Pull,
                Mode = "owner_to_target", Strength = 1f, RadiusTiles = 4f,
            } };
            var generated = Attach(new Projectile { owner = 0, active = true, timeLeft = 30 });
            generated.Configure(GeneratedItemData.Placeholder(), entity, 0, 3, Vector2.UnitX);
            var ledger = typeof(GeneratedProjectile).GetField("_activationSpawnBudget", BindingFlags.Instance | BindingFlags.NonPublic)!;
            Equal(true, ledger.GetValue(generated) is null, "remote projectile has no owner-local budget");
            generated.OnKill(20);
            using var stream = new MemoryStream();
            using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, leaveOpen: true))
                generated.SendExtraAI(writer);
            stream.Position = 0;
            using var reader = new BinaryReader(stream);
            reader.ReadByte(); // wire version
            reader.ReadString(); // generated item id
            reader.ReadString(); // entity id
            reader.ReadByte(); // child depth
            Equal((byte)3, reader.ReadByte(), "remote event preserves observed budget snapshot");
            Equal(true, ledger.GetValue(generated) is null, "remote event cannot mint even a zero-valued ledger");
        }
        finally
        {
            Terraria.Main.player[0] = priorOwner;
            Terraria.Main.netMode = priorMode;
            Terraria.Main.myPlayer = priorLocal;
        }
    }
}
