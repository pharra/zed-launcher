from __future__ import annotations

from zed_launcher.services import diagnose


def test_kwin_without_single_pixel_buffer_is_explained() -> None:
    hints = diagnose.analyse(
        [
            "No backend specified, automatically choosing Wayland because WAYLAND_DISPLAY is set",
            "kwin_wayland_backend: wp_single_pixel_buffer_manager_v1 isn't supported by the "
            "host compositor",
        ]
    )
    assert [hint["key"] for hint in hints] == ["kwin-protocols"]


def test_clean_output_has_no_hints() -> None:
    assert diagnose.analyse(["INFO: umu-launcher version 1.4.4", "fixme:ver:GetCurrentPackageId"]) == []
