"""APCA lightness contrast (Lc), reported as a supplementary readability metric.

Implements the APCA-W3 constants published as version ``0.0.98G-4g`` (the
"base" sRGB set used by the ``apca-w3`` reference package). APCA is not part
of any W3C Recommendation; it never replaces WCAG 2.x pass/fail here.
"""

from __future__ import annotations

from .color import RGB

APCA_VERSION = "0.0.98G-4g"

_MAIN_TRC = 2.4
_R_CO, _G_CO, _B_CO = 0.2126729, 0.7151522, 0.0721750
_NORM_BG, _NORM_TXT, _REV_TXT, _REV_BG = 0.56, 0.57, 0.62, 0.65
_BLK_THRS, _BLK_CLMP = 0.022, 1.414
_SCALE_BOW = _SCALE_WOB = 1.14
_LO_BOW_OFFSET = _LO_WOB_OFFSET = 0.027
_DELTA_Y_MIN = 0.0005
_LO_CLIP = 0.1


def apca_luminance(color: RGB) -> float:
    return float(
        _R_CO * color.r**_MAIN_TRC + _G_CO * color.g**_MAIN_TRC + _B_CO * color.b**_MAIN_TRC
    )


def apca_lc(text: RGB, background: RGB) -> float:
    """Return signed Lc: positive for dark text on light background, negative otherwise."""
    y_txt = apca_luminance(text)
    y_bg = apca_luminance(background)
    if y_txt <= _BLK_THRS:
        y_txt += (_BLK_THRS - y_txt) ** _BLK_CLMP
    if y_bg <= _BLK_THRS:
        y_bg += (_BLK_THRS - y_bg) ** _BLK_CLMP
    if abs(y_bg - y_txt) < _DELTA_Y_MIN:
        return 0.0
    if y_bg > y_txt:
        sapc = (y_bg**_NORM_BG - y_txt**_NORM_TXT) * _SCALE_BOW
        out = 0.0 if sapc < _LO_CLIP else sapc - _LO_BOW_OFFSET
    else:
        sapc = (y_bg**_REV_BG - y_txt**_REV_TXT) * _SCALE_WOB
        out = 0.0 if sapc > -_LO_CLIP else sapc + _LO_WOB_OFFSET
    return out * 100
