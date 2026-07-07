#nullable enable
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Sockets;
using System.Threading.Tasks;

namespace InfiniCrafterLocal.Common.Services;

/// <summary>
/// Shared throttle for expected local-helper HTTP failures.
///
/// tModLoader is very noisy when a background HTTP call repeatedly hits a closed
/// localhost port. The LocalGenerator helper can legitimately be stopped while the
/// player is in-world, so connection-refused should be treated as a quiet offline
/// state, not as a per-tick/game-chat exception storm.
/// </summary>
public static class LocalHttpQuietFailure
{
    private static readonly object LockObj = new();
    private static readonly Dictionary<string, DateTime> Cooldowns = new(StringComparer.OrdinalIgnoreCase);
    private static readonly Dictionary<string, string> LastMessages = new(StringComparer.OrdinalIgnoreCase);

    public static TimeSpan DefaultCooldown { get; set; } = TimeSpan.FromSeconds(45);

    public static bool ShouldSkip(string key)
    {
        if (string.IsNullOrWhiteSpace(key)) return false;
        lock (LockObj)
        {
            if (!Cooldowns.TryGetValue(key, out DateTime until)) return false;
            if (DateTime.UtcNow < until) return true;
            Cooldowns.Remove(key);
            return false;
        }
    }

    public static void Clear(string key)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        lock (LockObj)
        {
            Cooldowns.Remove(key);
            LastMessages.Remove(key);
        }
    }

    public static void ClearAll()
    {
        lock (LockObj)
        {
            Cooldowns.Clear();
            LastMessages.Clear();
        }
    }

    public static void Record(string key, Exception? ex, TimeSpan? cooldown = null)
    {
        if (string.IsNullOrWhiteSpace(key)) return;
        lock (LockObj)
        {
            Cooldowns[key] = DateTime.UtcNow + (cooldown ?? DefaultCooldown);
            LastMessages[key] = FriendlyMessage(ex);
        }
    }

    public static string LastMessage(string key)
    {
        if (string.IsNullOrWhiteSpace(key)) return "";
        lock (LockObj)
            return LastMessages.TryGetValue(key, out string? msg) ? msg ?? "" : "";
    }

    public static bool IsExpectedOffline(Exception? ex)
    {
        for (Exception? cur = ex; cur is not null; cur = cur.InnerException)
        {
            if (cur is OperationCanceledException || cur is TaskCanceledException)
                return true;
            if (cur is HttpRequestException)
                return true;
            if (cur is SocketException se)
            {
                if (se.SocketErrorCode is SocketError.ConnectionRefused
                    or SocketError.ConnectionReset
                    or SocketError.TimedOut
                    or SocketError.HostUnreachable
                    or SocketError.NetworkUnreachable
                    or SocketError.AddressNotAvailable)
                    return true;
            }
        }
        return false;
    }

    public static string FriendlyMessage(Exception? ex)
    {
        for (Exception? cur = ex; cur is not null; cur = cur.InnerException)
        {
            if (cur is SocketException se)
                return se.SocketErrorCode switch
                {
                    SocketError.ConnectionRefused => "LocalGenerator на этом порту не слушает",
                    SocketError.TimedOut => "LocalGenerator не ответил вовремя",
                    SocketError.HostUnreachable or SocketError.NetworkUnreachable => "LocalGenerator недоступен по сети",
                    _ => "LocalGenerator HTTP недоступен: " + se.SocketErrorCode,
                };
        }
        if (ex is OperationCanceledException || ex is TaskCanceledException)
            return "LocalGenerator не ответил вовремя";
        return ex?.Message ?? "LocalGenerator HTTP недоступен";
    }
}
