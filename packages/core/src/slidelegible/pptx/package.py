"""Read-only access to a validated PPTX (OOXML ZIP) package."""

from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass
from functools import cached_property

from lxml import etree

from ..errors import InvalidInput, ResourceLimitExceeded
from .xml import NS, parse_xml


@dataclass(frozen=True)
class PackageLimits:
    """Optional resource limits. ``None`` disables a limit (local single-user default)."""

    max_parts: int | None = 20_000
    max_part_bytes: int | None = None
    max_total_bytes: int | None = None
    max_compression_ratio: float | None = 200.0
    max_slides: int | None = None


DEFAULT_LIMITS = PackageLimits()


def _normalize_part(name: str) -> str:
    return name.lstrip("/")


class PptxPackage:
    """In-memory view of the package parts, with relationship helpers.

    Parts are kept as raw bytes so that unrelated parts can be copied to an
    output package byte-for-byte.
    """

    def __init__(self, data: bytes, limits: PackageLimits = DEFAULT_LIMITS) -> None:
        self.source_bytes = data
        self.fingerprint = hashlib.sha256(data).hexdigest()
        self.parts: dict[str, bytes] = {}
        self.part_order: list[str] = []
        self.zip_infos: dict[str, zipfile.ZipInfo] = {}
        self._xml_cache: dict[str, etree._Element] = {}
        self._load(data, limits)

    # --- loading -----------------------------------------------------------------
    def _load(self, data: bytes, limits: PackageLimits) -> None:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise InvalidInput("not_a_zip", "The file is not a valid .pptx (ZIP) package.") from exc
        infos = archive.infolist()
        if limits.max_parts is not None and len(infos) > limits.max_parts:
            raise ResourceLimitExceeded("too_many_parts", "The package contains too many parts.")
        total = 0
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            normalized = posixpath.normpath(name)
            if name.startswith("/") or "\\" in name or normalized.startswith(".."):
                raise InvalidInput("unsafe_path", f"Unsafe path in package: {name!r}")
            if limits.max_part_bytes is not None and info.file_size > limits.max_part_bytes:
                raise ResourceLimitExceeded("part_too_large", f"Package part too large: {name}")
            if (
                limits.max_compression_ratio is not None
                and info.compress_size > 0
                and info.file_size > 1_000_000
                and info.file_size / info.compress_size > limits.max_compression_ratio
            ):
                raise ResourceLimitExceeded(
                    "suspicious_compression", f"Suspicious compression ratio: {name}"
                )
            total += info.file_size
            if limits.max_total_bytes is not None and total > limits.max_total_bytes:
                raise ResourceLimitExceeded("package_too_large", "Expanded package too large.")
            try:
                self.parts[name] = archive.read(info)
            except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
                raise InvalidInput("corrupt_part", f"Cannot read package part {name}") from exc
            self.part_order.append(name)
            self.zip_infos[name] = info
        if "[Content_Types].xml" not in self.parts:
            raise InvalidInput("missing_content_types", "Missing [Content_Types].xml.")
        if self.presentation_part not in self.parts:
            raise InvalidInput("not_a_presentation", "This package is not a PowerPoint deck.")
        if self.is_encrypted:
            raise InvalidInput("encrypted", "Encrypted presentations are not supported.")
        if limits.max_slides is not None and len(self.slide_parts) > limits.max_slides:
            raise ResourceLimitExceeded("too_many_slides", "The presentation has too many slides.")

    # --- XML and relationships ---------------------------------------------------
    def xml(self, part: str) -> etree._Element:
        part = _normalize_part(part)
        cached = self._xml_cache.get(part)
        if cached is not None:
            return cached
        data = self.parts.get(part)
        if data is None:
            raise InvalidInput("missing_part", f"Missing package part: {part}")
        try:
            root = parse_xml(data)
        except etree.XMLSyntaxError as exc:
            raise InvalidInput("corrupt_xml", f"Malformed XML in {part}") from exc
        self._xml_cache[part] = root
        return root

    def has_part(self, part: str) -> bool:
        return _normalize_part(part) in self.parts

    @staticmethod
    def rels_part_for(part: str) -> str:
        directory, name = posixpath.split(_normalize_part(part))
        return posixpath.join(directory, "_rels", f"{name}.rels")

    def relationships(self, part: str) -> dict[str, tuple[str, str, bool]]:
        """Map rId -> (type, target part or URL, is_external)."""
        rels_name = self.rels_part_for(part)
        if rels_name not in self.parts:
            return {}
        root = self.xml(rels_name)
        base = posixpath.dirname(_normalize_part(part))
        result: dict[str, tuple[str, str, bool]] = {}
        for rel in root.findall("pr:Relationship", NS):
            rid = rel.get("Id")
            target = rel.get("Target") or ""
            rtype = rel.get("Type") or ""
            external = rel.get("TargetMode") == "External"
            if rid is None:
                continue
            if not external:
                if target.startswith("/"):
                    target = target.lstrip("/")
                else:
                    target = posixpath.normpath(posixpath.join(base, target))
            result[rid] = (rtype, target, external)
        return result

    def related_part(self, part: str, rtype_suffix: str) -> str | None:
        for rtype, target, external in self.relationships(part).values():
            if not external and rtype.endswith(rtype_suffix):
                return target
        return None

    # --- structure ---------------------------------------------------------------
    @cached_property
    def presentation_part(self) -> str:
        root_rels = self.parts.get("_rels/.rels")
        if root_rels is not None:
            for rel in parse_xml(root_rels).findall("pr:Relationship", NS):
                if (rel.get("Type") or "").endswith("/officeDocument"):
                    return (rel.get("Target") or "ppt/presentation.xml").lstrip("/")
        return "ppt/presentation.xml"

    @property
    def is_encrypted(self) -> bool:
        return "EncryptionInfo" in self.parts or "EncryptedPackage" in self.parts

    @cached_property
    def slide_parts(self) -> list[str]:
        pres = self.xml(self.presentation_part)
        rels = self.relationships(self.presentation_part)
        result: list[str] = []
        for sld_id in pres.findall("p:sldIdLst/p:sldId", NS):
            rid = sld_id.get(f"{{{NS['r']}}}id")
            if rid and rid in rels:
                result.append(rels[rid][1])
        return result

    @cached_property
    def slide_size(self) -> tuple[int, int]:
        sz = self.xml(self.presentation_part).find("p:sldSz", NS)
        if sz is None:
            return (9_144_000, 6_858_000)
        return (int(sz.get("cx", "9144000")), int(sz.get("cy", "6858000")))

    def layout_for(self, slide_part: str) -> str | None:
        return self.related_part(slide_part, "/slideLayout")

    def master_for(self, layout_part: str) -> str | None:
        return self.related_part(layout_part, "/slideMaster")

    def theme_for(self, master_part: str) -> str | None:
        return self.related_part(master_part, "/theme")

    @cached_property
    def table_styles_part(self) -> str | None:
        return self.related_part(self.presentation_part, "/tableStyles")
