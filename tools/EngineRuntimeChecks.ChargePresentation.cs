using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void ChargePresentationReadsActualClockAndSignalsOnce()
    {
        foreach (int extra in new[] { 0, 2 })
        {
            using var scope = new SwarmRuntimeScope();
            var data = UnitChargeFixture(4f, 3, 2f, extra);
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            var generated = SwarmHost(data, entity);
            Player owner = Terraria.Main.player[0];
            owner.inventory[0] = new Item(ItemID.WoodenSword);
            AttachItem(new GeneratedItem(), owner.inventory[0], data);
            owner.channel = true;
            Equal(false, generated.TryCaptureChargeStatus(owner, out _), "no charge presentation before actual controller activation");
            generated.AI();
            Equal(true, generated.TryCaptureChargeStatus(owner, out var first), "actual held charge produces status");
            Equal(3 * (extra + 1), first.DurationUpdates, "world duration follows exact native extraUpdates");
            Equal(1, first.ChargeUpdates, "actual accumulated subupdate counter");
            Equal(1f / first.DurationUpdates, first.Progress, "display ratio uses the same controller clock");
            string before = data.ToNetworkJson();
            generated.TryCaptureChargeStatus(owner, out var repeated);
            Equal(first, repeated, "repeated reads do not advance charge or alter source identity");
            Equal(before, data.ToNetworkJson(), "presentation never changes definition");
            var announced = new HashSet<object>();
            Equal(false, GeneratedChargeUISystem.ObserveReady(first, announced), "partial charge cannot signal readiness");
            for (int i = 1; i < first.DurationUpdates; i++) generated.AI();
            Equal(true, generated.TryCaptureChargeStatus(owner, out var full), "full charge remains visible while held");
            Equal(1f, full.Progress, "full charge reaches exactly one");
            Equal(true, GeneratedChargeUISystem.ObserveReady(full, announced), "first full observation signals");
            Equal(false, GeneratedChargeUISystem.ObserveReady(full, announced), "draws and subsequent ticks cannot replay signal");
            Equal(100, generated.Projectile.damage, "readiness indication does not release or scale damage");
            Equal(0, PendingActions(), "HUD does not publish gameplay channel-complete actions");
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            generated.TryCaptureChargeStatus(owner, out var hydrated);
            Equal(full.Source, hydrated.Source, "metadata hydration preserves physical presentation generation");
            Equal(false, GeneratedChargeUISystem.ObserveReady(hydrated, announced), "rehydration cannot replay ready sound");
            using var payload = new MemoryStream();
            using (var writer = new BinaryWriter(payload, System.Text.Encoding.UTF8, leaveOpen: true)) generated.SendExtraAI(writer);
            payload.Position = 0;
            using (var reader = new BinaryReader(payload, System.Text.Encoding.UTF8, leaveOpen: true)) generated.ReceiveExtraAI(reader);
            // The metadata registry may be absent in this isolated scope; direct
            // rehydration follows the same preserve-state path as late definitions.
            generated.Configure(data, entity, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Equal(true, generated.TryCaptureChargeStatus(owner, out var received), "synced full charge retains status");
            Equal(full.ChargeUpdates, received.ChargeUpdates, "ExtraAI retains existing charge counter");
            Equal(false, GeneratedChargeUISystem.ObserveReady(received, announced), "same physical ExtraAI cannot replay ready sound");
            owner.channel = false;
            generated.AI();
            Equal(false, generated.TryCaptureChargeStatus(owner, out _), "released projectile has no charge HUD");
            owner.channel = true;
            var next = SwarmHost(data, entity);
            for (int i = 0; i < first.DurationUpdates; i++) next.AI();
            next.TryCaptureChargeStatus(owner, out var nextStatus);
            Equal(false, ReferenceEquals(full.Source, nextStatus.Source), "replacement in same slot has a fresh generation");
            Equal(true, GeneratedChargeUISystem.ObserveReady(nextStatus, announced), "next physical charge may signal once");
            Equal(false, next.TryCaptureChargeStatus(Terraria.Main.player[1], out _), "foreign player cannot read another owner's held HUD");
            owner.dead = true;
            Equal(false, next.TryCaptureChargeStatus(owner, out _), "dead owner has no charge HUD");
            owner.dead = false; owner.inventory[0] = new Item(ItemID.Wood);
            Equal(false, next.TryCaptureChargeStatus(owner, out _), "switched-away item has no stale charge HUD");
        }
        using (var scope = new SwarmRuntimeScope())
        {
            var data = UnitChargeFixture(4, 3, 2, 0, delayTicks: 2);
            var generated = SwarmHost(data, data.RuntimeProgram.TryGetEntity("root")!);
            Player owner = Terraria.Main.player[0];
            owner.inventory[0] = new Item(ItemID.WoodenSword);
            AttachItem(new GeneratedItem(), owner.inventory[0], data); owner.channel = true;
            generated.AI();
            Equal(false, generated.TryCaptureChargeStatus(owner, out _), "activation delay is not charging");
            generated.AI();
            Equal(false, generated.TryCaptureChargeStatus(owner, out _), "final inert delayed update is not charging");
            generated.AI();
            Equal(true, generated.TryCaptureChargeStatus(owner, out _), "charge status starts with actual controller");
        }
    }

    private static void ChargePresentationBoundsAndLocalization()
    {
        foreach (var size in new[] { new Point(400, 300), new Point(1920, 1080) })
        foreach (var mouse in new[] { Point.Zero, new Point(size.X, size.Y) })
        {
            Rectangle bounds = GeneratedChargeUISystem.Bounds(mouse.X, mouse.Y, size.X, size.Y);
            Equal(true, bounds.Left >= 0 && bounds.Right <= size.X && bounds.Top >= 0
                && bounds.Bottom + 20 <= size.Y, "charge bar and caption remain inside viewport");
        }
        WithForgePresentationLanguages(locale =>
        {
            string ready = Terraria.Localization.Language.GetTextValue("Mods.InfiniCrafterLocal.ChargeUI.Ready");
            string partial = Terraria.Localization.Language.GetTextValue("Mods.InfiniCrafterLocal.ChargeUI.Progress", 50);
            Equal(locale == "ru-RU" ? "Готово" : "Ready", ready, "localized charge readiness");
            Equal(true, partial.Contains("50%") && !partial.Contains("Mods."), "localized partial percent");
        });
    }
}
