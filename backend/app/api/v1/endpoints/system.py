from fastapi import APIRouter

from app._version import __version__

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
