#nullable enable
using System;
using System.Collections.Generic;
using System.Text.Json;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Read-only diagnostics for strict JSON boundaries. The runtime behavior remains
/// fail-closed (null item / empty VFX), but agents and QA can inspect why the
/// payload was rejected instead of losing the exception in a blanket catch.
/// Successful parsing clears only its own boundary, so an unrelated later parse
/// cannot hide a still-relevant failure from another contract surface.
/// </summary>
public sealed record ContractJsonError(
    string Boundary,
    string ErrorType,
    string Message,
    string Path,
    long? LineNumber,
    long? BytePositionInLine,
    DateTimeOffset RecordedAtUtc);

public static class ContractJsonDiagnostics
{
    private static readonly object Gate = new();
    private static readonly Dictionary<string, ContractJsonError> Errors = new(StringComparer.Ordinal);

    public static ContractJsonError? LastError
    {
        get
        {
            lock (Gate)
            {
                ContractJsonError? latest = null;
                foreach (ContractJsonError error in Errors.Values)
                {
                    if (latest is null || error.RecordedAtUtc > latest.RecordedAtUtc)
                        latest = error;
                }
                return latest;
            }
        }
    }

    public static IReadOnlyDictionary<string, ContractJsonError> Snapshot()
    {
        lock (Gate)
            return new Dictionary<string, ContractJsonError>(Errors, StringComparer.Ordinal);
    }

    public static bool TryGet(string boundary, out ContractJsonError? error)
    {
        lock (Gate)
            return Errors.TryGetValue(boundary ?? "unknown", out error);
    }

    public static void Clear()
    {
        lock (Gate)
            Errors.Clear();
    }

    public static void Clear(string boundary)
    {
        lock (Gate)
            Errors.Remove(boundary ?? "unknown");
    }

    public static ContractJsonError Record(string boundary, Exception exception)
    {
        string safeBoundary = boundary ?? "unknown";
        JsonException? json = exception as JsonException;
        var error = new ContractJsonError(
            Boundary: safeBoundary,
            ErrorType: exception.GetType().Name,
            Message: exception.Message ?? "JSON contract rejected",
            Path: json?.Path ?? "",
            LineNumber: json?.LineNumber,
            BytePositionInLine: json?.BytePositionInLine,
            RecordedAtUtc: DateTimeOffset.UtcNow);
        lock (Gate)
            Errors[safeBoundary] = error;
        return error;
    }
}
