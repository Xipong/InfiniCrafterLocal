from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any


def local_ipv4_candidates() -> list[str]:
    """Return non-loopback IPv4 candidates for LAN/Radmin asset URLs."""
    ips: list[str] = []

    def add(ip: str) -> None:
        ip = (ip or "").strip()
        if not ip or ip.startswith("127.") or ip in ips:
            return
        if not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", ip):
            return
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return
        # 169.254/16 is an APIPA/link-local fallback, not a peer-reachable LAN or
        # Radmin address. Advertising it makes Terraria clients fetch assets from
        # an address that only exists on the host's local link.
        if address.version != 4 or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
            return
        ips.append(ip)

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
        finally:
            sock.close()
    except Exception:
        pass
    return ips


def radmin_ipv4_candidates() -> list[str]:
    """Radmin VPN commonly uses the 26.x.x.x IPv4 range."""
    return [ip for ip in local_ipv4_candidates() if ip.startswith("26.")]


def multiplayer_connect_info(
    *,
    local_generator_port: int,
    terraria_port: str,
    asset_public_base_url: str = "",
    asset_transport: str = "native",
    host: str = "127.0.0.1",
) -> dict[str, Any]:
    """Build the user-facing LAN/Radmin connection card.

    This module owns network discovery. The HTTP server only passes current env/config
    values, so endpoint code does not carry socket probing and friend-text assembly.
    """
    radmin = radmin_ipv4_candidates()
    lan = local_ipv4_candidates()
    best_ip = radmin[0] if radmin else (lan[0] if lan else "")
    asset_transport = "http" if str(asset_transport or "").strip().lower() == "http" else "native"
    asset_url = ((asset_public_base_url or "").strip().rstrip("/") or (f"http://{best_ip}:{local_generator_port}" if best_ip else "")) if asset_transport == "http" else ""
    terraria_port = str(terraria_port or "7777")
    asset_step = (
        f"3) Generated PNG скачиваются напрямую с host LocalGenerator: {asset_url or 'http://<мой Radmin IP>:5055'}/get_asset."
        if asset_transport == "http"
        else "3) Generated PNG передаются нативно внутри Terraria/tModLoader packets; LocalGenerator друзьям не нужен."
    )
    health_step = (
        f"4) Проверка host helper: {(asset_url or 'http://<мой Radmin IP>:5055')}/health"
        if asset_transport == "http"
        else "4) Для Native не открывай LocalGenerator наружу: отдельный HTTP port друзьям не нужен."
    )
    friend_text = (
        "Как подключиться к моей Terraria / InfiniCrafterLocal:\n"
        "1) Игровой мир можно открыть через Steam Invite/Join или через Radmin Join via IP.\n"
        f"2) Если через IP: Terraria/tModLoader → Multiplayer → Join via IP → {best_ip or '<мой Radmin IP 26.x.x.x>'} → Port {terraria_port}.\n"
        f"{asset_step}\n"
        f"{health_step}\n"
        "5) Крафт server-authoritative: клиентская станция шлёт хосту только два item-ref + requestId; LocalGenerator/LLM/Z-Image нужен только хосту."
    )
    return {
        "host": host,
        "localGeneratorPort": local_generator_port,
        "terrariaPort": terraria_port,
        "radminIps": radmin,
        "lanIps": lan,
        "recommendedIp": best_ip,
        "assetTransport": asset_transport,
        "assetPublicBaseUrl": asset_url,
        "assetHealthUrl": (asset_url.rstrip("/") + "/health") if asset_url else "",
        "terrariaJoin": {"ip": best_ip, "port": terraria_port},
        "transportPolicy": (
            "Craft and generated definitions are server-authoritative Terraria packets. Final PNG bytes use host LocalGenerator /get_asset with descriptor/SHA verification."
            if asset_transport == "http"
            else "Craft, generated definitions and final PNG bundles use native Terraria/tModLoader packets with descriptor/SHA verification."
        ) + " No prompts, raw dumps, LLM keys or intermediate generation pipeline are sent to peers.",
        "friendText": friend_text,
    }
