from __future__ import annotations

from pathlib import Path

import httpx

from app.core.config import settings


async def send_document_to_telegram(*, chat_id: int, file_path: Path, caption: str) -> None:
    if not settings.bot_token:
        raise RuntimeError("Telegram bot token is not configured")

    telegram_url = f"https://api.telegram.org/bot{settings.bot_token}/sendDocument"
    async with httpx.AsyncClient(timeout=30) as client:
        with file_path.open("rb") as handle:
            files = {"document": (file_path.name, handle, "application/octet-stream")}
            data = {"chat_id": str(chat_id), "caption": caption}
            response = await client.post(telegram_url, data=data, files=files)
            response.raise_for_status()
