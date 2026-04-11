"""OneDrive file operations via Microsoft Graph API."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def ensure_folder(access_token: str, folder_path: str) -> dict[str, Any]:
    """Create a folder (and parents) in OneDrive if it doesn't exist.

    Args:
        folder_path: Path like "/OpenClaw/Documents" (leading slash required).

    Returns:
        Graph DriveItem dict for the folder.
    """
    parts = [p for p in folder_path.strip("/").split("/") if p]
    current_path = ""

    item: dict[str, Any] = {}
    async with httpx.AsyncClient() as client:
        for part in parts:
            parent = f"root:/{current_path}" if current_path else "root"
            current_path = f"{current_path}/{part}" if current_path else part

            # Check if folder exists
            check_url = f"{GRAPH_URL}/me/drive/{parent}:/{part}"
            resp = await client.get(check_url, headers=_headers(access_token))

            if resp.status_code == 200:
                item = resp.json()
                continue

            # Create folder
            create_url = f"{GRAPH_URL}/me/drive/{parent}/children"
            resp = await client.post(
                create_url,
                headers={**_headers(access_token), "Content-Type": "application/json"},
                json={
                    "name": part,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "fail",
                },
            )
            if resp.status_code == 409:
                # Already exists (race condition) — fetch it
                resp = await client.get(check_url, headers=_headers(access_token))
                resp.raise_for_status()
            else:
                resp.raise_for_status()
            item = resp.json()

    return item


async def upload_file(
    access_token: str,
    folder_path: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Upload a file to OneDrive.

    Args:
        folder_path: OneDrive folder path (e.g., "/OpenClaw/Documents").
        filename: Name of the file to create.
        content: File bytes.
        content_type: MIME type.

    Returns:
        Graph DriveItem dict for the uploaded file.
    """
    # Ensure folder exists
    await ensure_folder(access_token, folder_path)

    clean_path = folder_path.strip("/")
    upload_url = f"{GRAPH_URL}/me/drive/root:/{clean_path}/{filename}:/content"

    async with httpx.AsyncClient() as client:
        resp = await client.put(
            upload_url,
            headers={
                **_headers(access_token),
                "Content-Type": content_type,
            },
            content=content,
        )
        resp.raise_for_status()
        item = resp.json()

    logger.info(
        "onedrive.upload path=%s/%s size=%d id=%s",
        folder_path,
        filename,
        len(content),
        item.get("id"),
    )
    return item


async def create_sharing_link(
    access_token: str,
    item_id: str,
    link_type: str = "view",
    scope: str = "organization",
) -> str:
    """Create a sharing link for a OneDrive item.

    Args:
        item_id: Graph DriveItem ID.
        link_type: "view" or "edit".
        scope: "organization" or "anonymous".

    Returns:
        The sharing URL.
    """
    url = f"{GRAPH_URL}/me/drive/items/{item_id}/createLink"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={**_headers(access_token), "Content-Type": "application/json"},
            json={"type": link_type, "scope": scope},
        )
        resp.raise_for_status()
        data = resp.json()

    link_url = data.get("link", {}).get("webUrl", "")
    logger.info("onedrive.share_link item_id=%s type=%s url=%s", item_id, link_type, link_url)
    return link_url


async def list_files(
    access_token: str,
    folder_path: str = "/",
) -> list[dict[str, Any]]:
    """List files in a OneDrive folder.

    Returns:
        List of simplified file info dicts.
    """
    clean_path = folder_path.strip("/")
    if clean_path:
        url = f"{GRAPH_URL}/me/drive/root:/{clean_path}:/children"
    else:
        url = f"{GRAPH_URL}/me/drive/root/children"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
        data = resp.json()

    items = []
    for item in data.get("value", []):
        items.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "size": item.get("size"),
                "is_folder": "folder" in item,
                "web_url": item.get("webUrl"),
                "last_modified": item.get("lastModifiedDateTime"),
                "mime_type": item.get("file", {}).get("mimeType"),
            }
        )
    return items


async def download_file(
    access_token: str,
    item_id: str,
) -> bytes:
    """Download a file from OneDrive by item ID."""
    url = f"{GRAPH_URL}/me/drive/items/{item_id}/content"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
        return resp.content


async def get_edit_url(
    access_token: str,
    item_id: str,
) -> str:
    """Get the web URL for editing a file in Office Online."""
    url = f"{GRAPH_URL}/me/drive/items/{item_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(access_token))
        resp.raise_for_status()
        return resp.json().get("webUrl", "")
