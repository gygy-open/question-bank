from fastapi import APIRouter, Depends

from app._version import __version__
from app.api import deps

router = APIRouter()

# GitHub repository the desktop releases are published to. The frontend uses
# this to query the latest release and prompt the user to update.
GITHUB_REPO = "gygy-open/question-bank"


@router.get("/version")
async def get_version() -> dict:
    """Return the running application version and its release repository.

    Public (no auth): the frontend compares this against the latest GitHub
    release tag to decide whether to show an "update available" prompt.
    """
    return {
        "version": __version__,
        "repo": GITHUB_REPO,
        "releases_url": f"https://github.com/{GITHUB_REPO}/releases/latest",
    }


def _lan_ip() -> str:
    """Best-effort primary LAN IPv4 address (no packets are actually sent)."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


@router.get("/network")
async def get_network_info(
    current_user=Depends(deps.get_current_active_user),
) -> dict:
    """Return LAN-sharing status and the address colleagues can use.

    Lets non-technical desktop users read the access URL directly in the UI
    instead of running ``ipconfig``. When sharing is off, no address is
    returned (the app is bound to 127.0.0.1 and only reachable locally).
    """
    import os

    from app.core.config import get_lan_share
    from app.services import mdns

    lan_share = get_lan_share()
    port = int(os.getenv("PORT", "8000"))
    ip = _lan_ip() if lan_share else None
    hostname = mdns.current_hostname() if lan_share else None
    return {
        "lan_share": lan_share,
        "port": port,
        "host_ip": ip,
        "lan_url": f"http://{ip}:{port}/" if ip else None,
        "lan_hostname": hostname,
        "lan_hostname_url": f"http://{hostname}:{port}/" if hostname else None,
    }
