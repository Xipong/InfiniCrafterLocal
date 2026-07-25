#nullable enable

namespace InfiniCrafterLocal.Common;

/// <summary>
/// Hard engine/performance/network bounds for the finite v5 runtime program.
/// These limits constrain explicit authored choices; they do not infer design.
/// </summary>
public static class InfiniRuntimeLimits
{
    public const string RuntimeApiCurrent = "infini.runtime-program.v5";
    public const int MaxSupportedMovementCode = 19;
    public const int MaxSupportedControllerCode = 3;
    public const int MaxSupportedEventActionCode = 7;

    public const int MaxRuntimeEntities = 12;
    public const int MaxRuntimeBindings = 8;
    public const int MaxRuntimeEventsPerEntity = 16;
    public const int MaxRuntimeChildDepth = 3;
    public const int MaxRuntimeEventSpawns = 32;
    public const int MaxRuntimeSpawnCount = 12;
    public const int MaxRuntimeLifetimeTicks = 21_600;
    public const int MaxRuntimeActiveProjectilesPerOwner = 96;
    public const int MaxRuntimePeriodicActionsPerTick = 16;
    public const int MaxRuntimeEventActionsPerProjectileTick = 24;

}
