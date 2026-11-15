from __future__ import annotations

from pathlib import Path

import pytest

from zed_launcher.services import icons, notify, sgdb


class FakeResponse:
    def __init__(self, payload, status=200, content=b""):
        self._payload = payload
        self.status_code = status
        self.content = content

    def json(self):
        return self._payload


def test_extract_icon_requires_exe(tmp_path: Path) -> None:
    plain = tmp_path / "game.sh"
    plain.write_text("#!/bin/sh")
    assert icons.extract_icon(plain, "abc") is None


def test_extract_icon_handles_non_pe(tmp_path: Path) -> None:
    fake = tmp_path / "game.exe"
    fake.write_bytes(b"MZ this is not a real executable")
    assert icons.extract_icon(fake, "abc") is None


def test_remove_icon(tmp_path: Path) -> None:
    from zed_launcher.paths import artwork_dir

    target = artwork_dir() / "icons" / "abc.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"ico")
    icons.remove_icon("abc")
    assert not target.exists()


def test_notify_available_and_send_without_display(monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert notify.send("title", "body") is False
    # Must never raise for any status/exit combination.
    notify.notify_game_exit("Game", "failed", 12, 1)
    notify.notify_game_exit("Game", "exited", 90, 0)


def test_sgdb_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("ZED_SGDB_API", raising=False)
    with pytest.raises(sgdb.SgdbError, match="API key"):
        sgdb.search("celeste", {"steamgriddb_api_key": ""})


def test_sgdb_search_and_grids(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(url)
        assert headers["Authorization"] == "Bearer test-key"
        if "/search/autocomplete/" in url:
            return FakeResponse({"success": True, "data": [{"id": 42, "name": "Celeste"}]})
        return FakeResponse(
            {
                "success": True,
                "data": [
                    {"id": 1, "url": "https://cdn.test/a.png", "thumb": "https://cdn.test/a_t.png"},
                    {"id": 2},
                ],
            }
        )

    monkeypatch.setattr(sgdb.httpx, "get", fake_get)
    config = {"steamgriddb_api_key": "test-key"}

    found = sgdb.search("celeste", config)
    assert found == [{"id": "42", "name": "Celeste"}]
    assert calls[0].endswith("/search/autocomplete/celeste")

    grids = sgdb.grids("42", config)
    assert grids == [
        {
            "id": "1",
            "url": "https://cdn.test/a.png",
            "thumb": "https://cdn.test/a_t.png",
            "width": None,
            "height": None,
        }
    ]


def test_sgdb_rejects_bad_key(monkeypatch) -> None:
    monkeypatch.setattr(
        sgdb.httpx, "get", lambda *a, **k: FakeResponse({"success": False}, status=401)
    )
    with pytest.raises(sgdb.SgdbError, match="rejected"):
        sgdb.search("x", {"steamgriddb_api_key": "bad"})


def test_sgdb_download_cover(monkeypatch, tmp_path: Path) -> None:
    from zed_launcher.paths import artwork_dir

    monkeypatch.setattr(
        sgdb.httpx, "get", lambda *a, **k: FakeResponse({}, content=b"image-bytes")
    )
    relative = sgdb.download_cover("game1", "https://cdn.test/cover.jpg")
    assert relative == "covers/game1.jpg"
    assert (artwork_dir() / relative).read_bytes() == b"image-bytes"


def test_sgdb_download_rejects_http(monkeypatch) -> None:
    with pytest.raises(sgdb.SgdbError, match="https"):
        sgdb.download_cover("game1", "http://insecure.test/a.png")


def _ico_bytes() -> bytes:
    """Build a real 16x16 ICO so the converter has something valid to decode."""

    Image = pytest.importorskip("PIL.Image")
    import io

    image = Image.new("RGBA", (16, 16), (220, 40, 60, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="ICO", sizes=[(16, 16)])
    return buffer.getvalue()


def test_extract_icon_writes_png(tmp_path: Path, monkeypatch) -> None:
    from zed_launcher.paths import artwork_dir

    ico = _ico_bytes()

    class FakeExtractor:
        def __init__(self, path):
            self.path = path

        def get_icon(self, num=0, resource_id=None):
            import io

            return io.BytesIO(ico)

    monkeypatch.setattr(icons, "_get_extractor", lambda path: FakeExtractor(path), raising=False)
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")

    with monkeypatch.context() as patch:
        import icoextract

        patch.setattr(icoextract, "IconExtractor", FakeExtractor)
        relative = icons.extract_icon(exe, "png-game")

    assert relative == "icons/png-game.png"
    written = artwork_dir() / relative
    assert written.exists()
    assert written.read_bytes().startswith(b"\x89PNG")


def test_notify_language_resolution(monkeypatch) -> None:
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    assert notify.resolve_language("zh") == "zh"
    assert notify.resolve_language("en") == "en"
    assert notify.resolve_language("auto") == "en"
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert notify.resolve_language("auto") == "zh"
    assert notify.resolve_language(None) == "zh"


def test_notify_game_exit_uses_chinese(monkeypatch) -> None:
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(notify, "send", lambda title, body="", **k: sent.append((title, body)) or True)
    notify.notify_game_exit("Celeste", "exited", 125, 0, language="zh")
    notify.notify_game_exit("Celeste", "failed", 45, 3, language="en")
    assert sent[0] == ("Celeste", "已退出，用时 2 分 5 秒")
    assert sent[1] == ("Celeste", "Failed after 45s (exit 3)")


def test_notify_uses_configured_binary(tmp_path: Path) -> None:
    script = tmp_path / "my-notify-send"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    assert notify.binary_path({"tool_paths": {"notify_send": str(script)}}) == str(script)
    # Without a configured path it falls back to PATH lookup.
    assert notify.binary_path({"tool_paths": {}}) is None or "notify-send" in (
        notify.binary_path({"tool_paths": {}}) or ""
    )
