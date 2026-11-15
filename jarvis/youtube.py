"""YouTube: busca e abertura de vídeos no navegador padrão."""
from __future__ import annotations

import html
import re
import urllib.parse

import requests

from .desktop import Desktop

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}

HOME = "https://www.youtube.com"
MUSIC = "https://music.youtube.com"

_VIDEO_ID = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_TITLE = re.compile(r'"title":\{"runs":\[\{"text":"([^"]{1,140})"')


def search_url(term: str) -> str:
    return f"{HOME}/results?search_query={urllib.parse.quote_plus(term)}"


def watch_url(video_id: str) -> str:
    return f"{HOME}/watch?v={video_id}"


def first_video(term: str, timeout: float = 8.0) -> dict | None:
    """Primeiro resultado da busca: {'id', 'title', 'url'} — ou None."""
    try:
        resp = requests.get(search_url(term), headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception:
        return None

    ids = _VIDEO_ID.findall(resp.text)
    if not ids:
        return None

    title = ""
    match = _TITLE.search(resp.text)
    if match:
        title = html.unescape(match.group(1).replace("\\u0026", "&")).strip()
    return {"id": ids[0], "title": title, "url": watch_url(ids[0])}


def open_url(url: str) -> bool:
    """Abre uma URL no navegador padrão (Wayland/GNOME)."""
    return Desktop.open_url(url)
