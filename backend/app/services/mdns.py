"""Advertises the desktop app on the LAN via mDNS (Bonjour/Avahi).

Lets colleagues reach the app as ``http://questionbank.local:PORT/`` instead
of having to read the host's IP off the tray menu. Best-effort only: mDNS
depends on multicast reaching the client (blocked on some corporate/guest
Wi-Fi, and unreliably resolved on Android), so the IP address must always
stay available as a fallback alongside this.
"""

from __future__ import annotations

import socket
import threading

HOSTNAME = "questionbank.local."
_SERVICE_NAME = "questionbank._http._tcp.local."
_SERVICE_TYPE = "_http._tcp.local."

_lock = threading.Lock()
_zeroconf = None
_service_info = None


def start(ip: str, port: int) -> str | None:
    """Register ``questionbank.local`` -> ``ip:port``; returns the hostname on success."""
    global _zeroconf, _service_info
    with _lock:
        _stop_locked()
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            return None
        try:
            info = ServiceInfo(
                _SERVICE_TYPE,
                _SERVICE_NAME,
                addresses=[socket.inet_aton(ip)],
                port=port,
                server=HOSTNAME,
            )
            zc = Zeroconf()
            zc.register_service(info, allow_name_change=True)
        except Exception:  # noqa: BLE001 - mDNS registration is best-effort
            return None
        _zeroconf = zc
        _service_info = info
        return HOSTNAME.rstrip(".")


def _stop_locked() -> None:
    global _zeroconf, _service_info
    if _zeroconf is not None:
        try:
            if _service_info is not None:
                _zeroconf.unregister_service(_service_info)
            _zeroconf.close()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass
    _zeroconf = None
    _service_info = None


def stop() -> None:
    """Unregister the previously advertised hostname, if any."""
    with _lock:
        _stop_locked()


def current_hostname() -> str | None:
    """The advertised hostname (without trailing dot), or ``None`` if inactive."""
    return HOSTNAME.rstrip(".") if _zeroconf is not None else None
