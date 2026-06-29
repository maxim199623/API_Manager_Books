from api_manager_books.api.download_headers import content_disposition_attachment


def test_content_disposition_removes_raw_cr_lf():
    """Проверяет удаление CR/LF из имени файла."""
    header = content_disposition_attachment("bad\r\nname.txt", fallback="file.bin")

    assert "\r" not in header
    assert "\n" not in header
    assert 'filename="badname.txt"' in header


def test_content_disposition_removes_quote_and_backslash_from_fallback_filename():
    """Проверяет безопасный quoted filename."""
    header = content_disposition_attachment('bad"name\\test.txt', fallback="file.bin")
    quoted = header.split('filename="', 1)[1].split('"', 1)[0]

    assert '"' not in quoted
    assert "\\" not in quoted
    assert "bad-name-test.txt" in quoted


def test_content_disposition_adds_rfc5987_filename_for_unicode():
    """Проверяет percent-encoded Unicode имя."""
    header = content_disposition_attachment("глава 1.txt", fallback="file.bin")

    assert 'filename="' in header
    assert "filename*=UTF-8''%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0%201.txt" in header


def test_content_disposition_uses_fallback_for_empty_name():
    """Проверяет детерминированный fallback."""
    header = content_disposition_attachment("\r\n\t", fallback="file.bin")

    assert header == 'attachment; filename="file.bin"'


def test_content_disposition_caps_very_long_display_filename():
    """Проверяет ограничение длинного display имени."""
    header = content_disposition_attachment("a" * 300 + ".txt", fallback="file.bin")
    quoted = header.split('filename="', 1)[1].split('"', 1)[0]

    assert len(quoted) == 180
