#nullable enable

namespace InfiniCrafterLocal.Common;

/// <summary>
/// Cross-runtime constants shared by generated item loading and projectile execution.
/// Keep these here so C# validation, sync and gameplay do not drift independently.
/// </summary>
public static class InfiniRuntimeLimits
{
    public const string RuntimeApiCurrent = "v0.4.52";
    public const int MaxSupportedMovementCode = 18;
    public const int MaxSupportedEffectCode = 15;
    public const int MaxSupportedOnHitCode = 19;
    public const int NetProseMaxChars = 0;
}
