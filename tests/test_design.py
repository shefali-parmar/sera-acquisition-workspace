"""Readable palette and catalog naming compatibility, without model calls."""

import re

import pytest

from sera.ai import investigation_ids
from sera.catalog import load_practices
from sera.design import APP_CSS, BACKGROUND, MUTED_TEXT, SOFT_BACKGROUND, TEAL_TEXT, TEXT


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    high, low = sorted([luminance(foreground), luminance(background)], reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(
    "foreground,background",
    [
        (TEXT, BACKGROUND),
        (MUTED_TEXT, BACKGROUND),
        (MUTED_TEXT, SOFT_BACKGROUND),
        (TEAL_TEXT, SOFT_BACKGROUND),
        (TEAL_TEXT, BACKGROUND),
    ],
)
def test_small_text_palette_meets_normal_text_contrast(foreground, background):
    assert contrast_ratio(foreground, background) >= 4.5


def test_distinct_fictional_names_resolve_to_unchanged_stable_ids():
    practices = load_practices()
    assert len(practices) == 50
    assert len({practice.name.casefold() for practice in practices}) == len(practices)
    for index, practice in enumerate(practices, 1):
        assert practice.id == f"SERA-{index:03d}"
        assert not re.search(r"\s+\d+$", practice.name)
        assert investigation_ids(f"Investigate {practice.name}", [], None) == [practice.id]
        assert all(source.id.startswith(practice.id + "-S") for source in practice.sources)
        assert practice.fictional is True


def test_mobile_dialog_resets_native_position_to_viewport():
    # Native dialog offsets must not shift a viewport-sized panel off screen.
    mobile = APP_CSS.split("@media(max-width:700px)", 1)[1]
    match = re.search(r'\[role="dialog"\]\{([^}]+)\}', mobile)
    assert match is not None
    declarations = dict(
        declaration.split(":", 1) for declaration in match[1].split(";") if declaration
    )
    for property_name, value in {
        "position": "fixed!important",
        "inset": "0!important",
        "transform": "none!important",
        "box-sizing": "border-box",
        "background": "#F7F9F8!important",
        "width": "100vw!important",
        "height": "100dvh!important",
        "margin": "0!important",
        "border-radius": "0!important",
        "overflow-y": "auto",
    }.items():
        assert declarations[property_name] == value


def test_desktop_dialog_keeps_readable_bounded_width():
    desktop = APP_CSS.split("@media(max-width:700px)", 1)[0]
    match = re.search(r'\[role="dialog"\]\{([^}]+)\}', desktop)
    assert match is not None
    assert "max-width:1000px!important" in match[1]
    assert "width:calc(100vw - 48px)!important" in match[1]
    assert "position:fixed" not in match[1]
