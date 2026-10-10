#nullable enable
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.Runtime;

// Exact context supplied by a registered emission adapter. It has no defaults,
// target selection, velocity sampler or movement policy of its own.
internal readonly record struct RuntimeSpawnTransform(Vector2 Position, Vector2 Direction)
{
    internal bool IsValid => float.IsFinite(Position.X) && float.IsFinite(Position.Y)
        && float.IsFinite(Direction.X) && float.IsFinite(Direction.Y)
        && float.IsFinite(Direction.LengthSquared()) && Direction.LengthSquared() > 0f;
}
