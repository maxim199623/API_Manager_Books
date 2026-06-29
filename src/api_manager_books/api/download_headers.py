from urllib.parse import quote


def _sanitize_display_filename(filename: str | None) -> str:
    text = filename or ""
    without_controls = "".join(ch for ch in text if ord(ch) >= 32 and ord(ch) != 127)
    safe = without_controls.replace('"', "-").replace("\\", "-").strip()
    return safe[:180]


def content_disposition_attachment(filename: str | None, *, fallback: str) -> str:
    """Формирует безопасный Content-Disposition для скачивания."""
    display_name = _sanitize_display_filename(filename)
    if not display_name:
        display_name = _sanitize_display_filename(fallback) or "download.bin"

    ascii_name = display_name.encode("ascii", "ignore").decode().strip()
    if not ascii_name:
        ascii_name = _sanitize_display_filename(fallback).encode("ascii", "ignore").decode().strip()
    if not ascii_name:
        ascii_name = "download.bin"
    ascii_name = ascii_name[:180]

    header = f'attachment; filename="{ascii_name}"'
    if any(ord(ch) > 127 for ch in filename or display_name):
        encoded_name = quote(display_name, safe="")
        header += f"; filename*=UTF-8''{encoded_name}"
    return header
