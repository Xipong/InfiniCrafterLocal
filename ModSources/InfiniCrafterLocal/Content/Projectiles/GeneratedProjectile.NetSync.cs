#nullable enable
using Microsoft.Xna.Framework;
using System;
using System.IO;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private const byte RuntimeNetVersion = 1;

    public override void SendExtraAI(BinaryWriter writer)
    {
        writer.Write(RuntimeNetVersion);
        writer.Write(_generatedItemId ?? "");
        writer.Write(_entityId ?? "");
        writer.Write((byte)Math.Clamp(_childDepth, 0, 255));
        writer.Write((byte)Math.Clamp(_remainingSpawnBudget, 0, 255));
        writer.Write(_initialDirection.X);
        writer.Write(_initialDirection.Y);
        writer.Write(_age);
        writer.Write(_remainingBounces);
        writer.Write(_activationDelayTicks);
        writer.Write(_returning);
        writer.Write(_released);
        writer.Write(_chargeTicks);
        writer.Write(_controllerTimer);
        writer.Write(_lastTarget);
    }

    public override void ReceiveExtraAI(BinaryReader reader)
    {
        try
        {
            if (reader.ReadByte() != RuntimeNetVersion)
                throw new InvalidDataException("unsupported generated runtime projectile payload");
            _generatedItemId = (reader.ReadString() ?? "").Trim();
            _entityId = (reader.ReadString() ?? "").Trim();
            if (_generatedItemId.Length > 96 || _entityId.Length > 48)
                throw new InvalidDataException("generated runtime projectile identity too long");
            _childDepth = reader.ReadByte();
            _remainingSpawnBudget = reader.ReadByte();
            _initialDirection = new Vector2(reader.ReadSingle(), reader.ReadSingle()).SafeNormalize(Vector2.UnitX);
            _age = Math.Max(0, reader.ReadInt32());
            _remainingBounces = Math.Max(0, reader.ReadInt32());
            _activationDelayTicks = Math.Max(0, reader.ReadInt32());
            _returning = reader.ReadBoolean();
            _released = reader.ReadBoolean();
            _chargeTicks = Math.Max(0, reader.ReadInt32());
            _controllerTimer = Math.Max(0, reader.ReadInt32());
            _lastTarget = reader.ReadInt32();
            _configured = false;
            TryHydrate();
        }
        catch
        {
            _configured = false;
            Projectile.friendly = false;
            Projectile.velocity = Vector2.Zero;
            Projectile.timeLeft = Math.Min(Projectile.timeLeft, 30);
        }
    }
}
