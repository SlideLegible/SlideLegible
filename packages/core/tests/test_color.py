"""Reference-vector tests for color math."""

from __future__ import annotations

import pytest
from slidelegible.apca import apca_lc
from slidelegible.color import (
    OKLCH,
    RGB,
    composite,
    contrast_ratio,
    oklch_in_gamut,
    oklch_to_rgb,
    relative_luminance,
    rgb_to_oklch,
)

WHITE = RGB.from_hex("FFFFFF")
BLACK = RGB.from_hex("000000")


def test_hex_round_trip() -> None:
    assert RGB.from_hex("#1a2B3c").hex == "1A2B3C"
    assert RGB.from_hex("fff").hex == "FFFFFF"
    with pytest.raises(ValueError):
        RGB.from_hex("12345")


@pytest.mark.parametrize(
    ("fg", "bg", "expected"),
    [
        ("000000", "FFFFFF", 21.0),
        ("FFFFFF", "FFFFFF", 1.0),
        ("777777", "FFFFFF", 4.48),  # WebAIM: just below AA
        ("767676", "FFFFFF", 4.54),  # WebAIM: smallest gray passing AA on white
        ("0000FF", "FFFFFF", 8.59),
        ("FF0000", "FFFFFF", 4.0),
        ("B0B0B0", "1E1E1E", 7.69),
    ],
)
def test_wcag_contrast_reference_pairs(fg: str, bg: str, expected: float) -> None:
    assert contrast_ratio(RGB.from_hex(fg), RGB.from_hex(bg)) == pytest.approx(expected, abs=0.01)


def test_contrast_is_symmetric_and_bounded() -> None:
    a, b = RGB.from_hex("336699"), RGB.from_hex("FFCC00")
    assert contrast_ratio(a, b) == contrast_ratio(b, a)
    assert relative_luminance(BLACK) == 0
    assert relative_luminance(WHITE) == pytest.approx(1)


def test_threshold_is_not_rounded() -> None:
    assert contrast_ratio(RGB.from_hex("777777"), WHITE) < 4.5


@pytest.mark.parametrize(
    ("text", "bg", "expected"),
    [
        ("888888", "FFFFFF", 63.06),
        ("FFFFFF", "888888", -68.54),
        ("000000", "FFFFFF", 106.04),
        ("FFFFFF", "000000", -107.88),
        ("B0B0B0", "1E1E1E", -57.7),
        ("FFFFFF", "777777", -76.6),
    ],
)
def test_apca_reference_values(text: str, bg: str, expected: float) -> None:
    assert apca_lc(RGB.from_hex(text), RGB.from_hex(bg)) == pytest.approx(expected, abs=0.15)


def test_composite_half_black_over_white() -> None:
    out = composite(BLACK.with_alpha(0.5), WHITE)
    assert out.alpha == 1
    assert out.hex == "808080"


def test_composite_transparent_top_keeps_bottom() -> None:
    bottom = RGB.from_hex("123456")
    assert composite(WHITE.with_alpha(0), bottom).hex == "123456"


@pytest.mark.parametrize(
    ("hex_value", "lightness", "chroma", "hue"),
    [
        # Reference values from the OKLCH definition (Ottosson) as used by CSS Color 4.
        ("FFFFFF", 1.0, 0.0, None),
        ("000000", 0.0, 0.0, None),
        ("FF0000", 0.62796, 0.25768, 29.23),
        ("00FF00", 0.86644, 0.29483, 142.50),
        ("0000FF", 0.45201, 0.31321, 264.05),
    ],
)
def test_oklch_reference_vectors(
    hex_value: str, lightness: float, chroma: float, hue: float | None
) -> None:
    value = rgb_to_oklch(RGB.from_hex(hex_value))
    assert value.l == pytest.approx(lightness, abs=1e-3)
    assert value.c == pytest.approx(chroma, abs=1e-3)
    if hue is not None:
        assert value.h == pytest.approx(hue, abs=0.1)


@pytest.mark.parametrize("hex_value", ["336699", "FFCC00", "7F7F7F", "E91E63", "010203"])
def test_oklch_round_trip(hex_value: str) -> None:
    color = RGB.from_hex(hex_value)
    assert oklch_to_rgb(rgb_to_oklch(color)).hex == hex_value


def test_out_of_gamut_keeps_lightness_and_hue() -> None:
    wanted = OKLCH(0.9, 0.3, 264.0)
    assert not oklch_in_gamut(wanted)
    mapped = rgb_to_oklch(oklch_to_rgb(wanted))
    assert mapped.l == pytest.approx(0.9, abs=2e-3)
    assert mapped.h == pytest.approx(264.0, abs=1.0)
    assert mapped.c < 0.3
