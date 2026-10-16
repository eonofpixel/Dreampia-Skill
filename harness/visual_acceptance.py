"""Deterministic PNG structure, scanline pixel decoding, and visual acceptance verification.

Dreampia Skill native visual governance module.
Follows SOLID principles:
- PngDecoder: Single responsibility for PNG chunk/CRC/zlib/scanline decoding
- VisualComparator: Single responsibility for baseline vs candidate pixel comparison
- VisualAcceptanceGate: Single responsibility for manifest-based visual acceptance checks
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS_BY_COLOR_TYPE: dict[int, int] = {0: 1, 2: 3, 4: 2, 6: 4}
MAX_DIMENSION = 16384
MAX_PIXELS = 33_554_432


class VisualAcceptanceError(ValueError):
    """시각 검증 입력 또는 PNG 구조 오류 예외."""

    code = "VISUAL_INPUT_INVALID"


@dataclass(frozen=True)
class PngImage:
    width: int
    height: int
    color_type: int
    channels: int
    pixels: bytes
    sha256: str


@dataclass(frozen=True)
class VisualDiffResult:
    status: str
    identical_bytes: bool
    identical_pixels: bool
    dimensions_match: bool
    baseline_size: list[int]
    candidate_size: list[int]
    changed_pixels: int
    total_pixels: int
    changed_pixel_ratio: float
    max_channel_delta: int
    mean_channel_delta: float
    max_diff_ratio: float
    baseline_sha256: str
    candidate_sha256: str
    message_ko: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "identical_bytes": self.identical_bytes,
            "identical_pixels": self.identical_pixels,
            "dimensions_match": self.dimensions_match,
            "baseline_size": self.baseline_size,
            "candidate_size": self.candidate_size,
            "changed_pixels": self.changed_pixels,
            "total_pixels": self.total_pixels,
            "changed_pixel_ratio": self.changed_pixel_ratio,
            "max_channel_delta": self.max_channel_delta,
            "mean_channel_delta": self.mean_channel_delta,
            "max_diff_ratio": self.max_diff_ratio,
            "baseline_sha256": self.baseline_sha256,
            "candidate_sha256": self.candidate_sha256,
            "message_ko": self.message_ko,
        }


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanlines(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    expected = height * (1 + stride)
    if len(raw) != expected:
        raise VisualAcceptanceError("PNG 스캔라인 압축 해제 길이가 이미지 크기와 일치하지 않습니다.")
    output = bytearray(height * stride)
    for row in range(height):
        row_start = row * (1 + stride)
        filter_type = raw[row_start]
        src = raw[row_start + 1 : row_start + 1 + stride]
        dst_offset = row * stride
        prev_offset = (row - 1) * stride
        for i in range(stride):
            byte = src[i]
            left = output[dst_offset + i - bpp] if i >= bpp else 0
            up = output[prev_offset + i] if row > 0 else 0
            up_left = output[prev_offset + i - bpp] if row > 0 and i >= bpp else 0
            if filter_type == 0:
                val = byte
            elif filter_type == 1:
                val = (byte + left) & 0xFF
            elif filter_type == 2:
                val = (byte + up) & 0xFF
            elif filter_type == 3:
                val = (byte + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                val = (byte + _paeth(left, up, up_left)) & 0xFF
            else:
                raise VisualAcceptanceError(f"지원하지 않는 PNG 필터 타입입니다: {filter_type}")
            output[dst_offset + i] = val
    return bytes(output)


def decode_png_bytes(data: bytes) -> PngImage:
    """바이트 배열에서 PNG 청크, CRC, IHDR/IDAT/IEND 및 픽셀 데이터를 결정론적으로 검증하고 디코딩한다."""
    if not data.startswith(PNG_SIGNATURE):
        raise VisualAcceptanceError("유효한 PNG 시그니처가 아닙니다.")
    offset = len(PNG_SIGNATURE)
    width = height = color_type = None
    idat_chunks: list[bytes] = []
    seen_ihdr = False
    seen_idat = False
    seen_iend = False
    while offset < len(data):
        if seen_iend:
            raise VisualAcceptanceError("IEND 청크 이후에 불필요한 데이터가 존재합니다.")
        if offset + 8 > len(data):
            raise VisualAcceptanceError("PNG 청크 헤더가 손상되었거나 잘렸습니다.")
        length, chunk_type = struct.unpack(">I4s", data[offset : offset + 8])
        offset += 8
        if offset + length + 4 > len(data):
            raise VisualAcceptanceError("PNG 청크 본문이 손상되었거나 잘렸습니다.")
        chunk_data = data[offset : offset + length]
        offset += length
        (expected_crc,) = struct.unpack(">I", data[offset : offset + 4])
        offset += 4
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise VisualAcceptanceError(f"PNG 청크 CRC 불일치: {chunk_type.decode('ascii', errors='replace')}")
        if not seen_ihdr and chunk_type != b"IHDR":
            raise VisualAcceptanceError("PNG 파일의 첫 번째 청크는 반드시 IHDR이어야 합니다.")
        if chunk_type == b"IHDR":
            if seen_ihdr or length != 13:
                raise VisualAcceptanceError("유효하지 않은 IHDR 청크입니다.")
            seen_ihdr = True
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if width <= 0 or height <= 0:
                raise VisualAcceptanceError("PNG 가로/세로 크기는 양수여야 합니다.")
            if width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
                raise VisualAcceptanceError("PNG 해상도가 허용된 안전 한도를 초과했습니다.")
            if bit_depth != 8 or color_type not in CHANNELS_BY_COLOR_TYPE:
                raise VisualAcceptanceError("시각 검증은 8-bit 그레이스케일/RGB/RGBA PNG만 지원합니다.")
            if compression != 0 or filter_method != 0 or interlace != 0:
                raise VisualAcceptanceError("지원하지 않는 PNG 압축/필터/인터레이스 모드입니다.")
        elif chunk_type == b"IDAT":
            if not seen_ihdr:
                raise VisualAcceptanceError("IHDR 이전에 IDAT 청크가 나타났습니다.")
            seen_idat = True
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            if not seen_ihdr or not seen_idat or length != 0:
                raise VisualAcceptanceError("유효하지 않은 IEND 청크입니다.")
            seen_iend = True
    if width is None or height is None or color_type is None or not idat_chunks or not seen_iend:
        raise VisualAcceptanceError("PNG 필수 청크(IHDR, IDAT, IEND)가 누락되었습니다.")
    channels = CHANNELS_BY_COLOR_TYPE[color_type]
    expected_raw = height * (1 + width * channels)
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(b"".join(idat_chunks), expected_raw + 1)
        tail = decompressor.flush()
    except zlib.error as exc:
        raise VisualAcceptanceError("PNG IDAT zlib 압축 해제에 실패했습니다.") from exc
    if len(raw) > expected_raw or len(raw) + len(tail) != expected_raw or decompressor.unconsumed_tail:
        raise VisualAcceptanceError("PNG 압축 해제 스트림 길이가 유효하지 않습니다.")
    raw += tail
    pixels = _unfilter_scanlines(raw, width, height, channels)
    return PngImage(
        width=width,
        height=height,
        color_type=color_type,
        channels=channels,
        pixels=pixels,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def read_png(path: Path) -> PngImage:
    """안전하게 일반 파일 여부를 확인한 뒤 PNG를 디코딩한다."""
    if path.is_symlink() or not path.is_file():
        raise VisualAcceptanceError(f"일반 PNG 파일이 필요합니다: {path}")
    return decode_png_bytes(path.read_bytes())


def validate_png_bytes(data: bytes) -> dict[str, object]:
    """PNG 바이트의 청크·CRC·픽셀 무결성을 검증하고 메타데이터를 반환한다."""
    img = decode_png_bytes(data)
    return {
        "valid": True,
        "width": img.width,
        "height": img.height,
        "color_type": img.color_type,
        "channels": img.channels,
        "sha256": img.sha256,
    }


def _to_rgba(image: PngImage) -> bytes:
    if image.color_type == 6:
        return image.pixels
    out = bytearray(image.width * image.height * 4)
    src = image.pixels
    pixel_count = image.width * image.height
    for idx in range(pixel_count):
        dst = idx * 4
        if image.color_type == 0:
            v = src[idx]
            out[dst : dst + 4] = bytes((v, v, v, 255))
        elif image.color_type == 4:
            v = src[idx * 2]
            a = src[idx * 2 + 1]
            out[dst : dst + 4] = bytes((v, v, v, a))
        elif image.color_type == 2:
            s = idx * 3
            out[dst : dst + 4] = bytes((src[s], src[s + 1], src[s + 2], 255))
    return bytes(out)


def compare_visuals(
    baseline_path: Path,
    candidate_path: Path,
    max_diff_ratio: float = 0.0,
) -> dict[str, object]:
    """베이스라인과 후보 PNG 이미지를 픽셀 단위로 비교한다."""
    if type(max_diff_ratio) not in (int, float) or max_diff_ratio < 0.0 or max_diff_ratio > 1.0:
        raise VisualAcceptanceError("max_diff_ratio는 0.0 이상 1.0 이하의 숫자여야 합니다.")
    base = read_png(baseline_path)
    cand = read_png(candidate_path)
    if (base.width, base.height) != (cand.width, cand.height):
        return VisualDiffResult(
            status="FAIL",
            identical_bytes=False,
            identical_pixels=False,
            dimensions_match=False,
            baseline_size=[base.width, base.height],
            candidate_size=[cand.width, cand.height],
            changed_pixels=max(base.width * base.height, cand.width * cand.height),
            total_pixels=max(base.width * base.height, cand.width * cand.height),
            changed_pixel_ratio=1.0,
            max_channel_delta=255,
            mean_channel_delta=255.0,
            max_diff_ratio=float(max_diff_ratio),
            baseline_sha256=base.sha256,
            candidate_sha256=cand.sha256,
            message_ko="베이스라인과 후보 이미지의 해상도가 일치하지 않습니다.",
        ).to_dict()

    base_rgba = _to_rgba(base)
    cand_rgba = _to_rgba(cand)
    total_pixels = base.width * base.height
    changed_pixels = 0
    max_delta = 0
    channel_delta_sum = 0
    for idx in range(0, len(base_rgba), 4):
        d0 = abs(base_rgba[idx] - cand_rgba[idx])
        d1 = abs(base_rgba[idx + 1] - cand_rgba[idx + 1])
        d2 = abs(base_rgba[idx + 2] - cand_rgba[idx + 2])
        d3 = abs(base_rgba[idx + 3] - cand_rgba[idx + 3])
        pixel_max = max(d0, d1, d2, d3)
        if pixel_max:
            changed_pixels += 1
            if pixel_max > max_delta:
                max_delta = pixel_max
            channel_delta_sum += d0 + d1 + d2 + d3
    ratio = changed_pixels / total_pixels if total_pixels else 0.0
    mean_delta = channel_delta_sum / (total_pixels * 4) if total_pixels else 0.0
    passed = ratio <= max_diff_ratio
    return VisualDiffResult(
        status="PASS" if passed else "FAIL",
        identical_bytes=base.sha256 == cand.sha256,
        identical_pixels=changed_pixels == 0,
        dimensions_match=True,
        baseline_size=[base.width, base.height],
        candidate_size=[cand.width, cand.height],
        changed_pixels=changed_pixels,
        total_pixels=total_pixels,
        changed_pixel_ratio=round(ratio, 8),
        max_channel_delta=max_delta,
        mean_channel_delta=round(mean_delta, 8),
        max_diff_ratio=float(max_diff_ratio),
        baseline_sha256=base.sha256,
        candidate_sha256=cand.sha256,
        message_ko="시각 허용 기준을 통과했습니다." if passed else "픽셀 변경 비율이 허용 임계치를 초과했습니다.",
    ).to_dict()


def _safe_relative_path(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or "\\" in rel or "\x00" in rel:
        raise VisualAcceptanceError("유효하지 않은 상대 경로입니다.")
    parts = Path(rel).parts
    if Path(rel).is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise VisualAcceptanceError("시각 검증 경로가 루트 외부로 벗어납니다.")
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise VisualAcceptanceError("시각 검증 경로에 심볼릭 링크를 사용할 수 없습니다.")
    resolved = current.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise VisualAcceptanceError("시각 검증 경로가 루트 외부로 벗어납니다.") from exc
    return resolved


def verify_visual_acceptance(manifest_path: Path, root: Path | None = None) -> dict[str, object]:
    """시각 검증 매니페스트(schema_version 1)의 모든 비교 항목을 검증한다."""
    manifest_file = manifest_path.resolve()
    if manifest_path.is_symlink() or not manifest_file.is_file():
        raise VisualAcceptanceError("시각 검증 매니페스트 일반 파일이 필요합니다.")
    base_root = (root or manifest_file.parent).resolve()
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "checks"}:
        raise VisualAcceptanceError("유효하지 않은 시각 검증 매니페스트 필드입니다.")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise VisualAcceptanceError("지원하지 않는 시각 검증 스키마 버전입니다.")
    checks = data["checks"]
    if not isinstance(checks, list) or not checks:
        raise VisualAcceptanceError("시각 검증 항목(checks)은 비어 있지 않은 배열이어야 합니다.")
    results: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for row in checks:
        if not isinstance(row, dict) or set(row) != {"id", "baseline", "candidate", "max_diff_ratio"}:
            raise VisualAcceptanceError("시각 검증 항목 필드가 올바르지 않습니다.")
        check_id = row["id"]
        if not isinstance(check_id, str) or not check_id.strip() or check_id in seen_ids:
            raise VisualAcceptanceError("중복되었거나 비어 있는 시각 검증 ID입니다.")
        seen_ids.add(check_id)
        baseline = _safe_relative_path(base_root, row["baseline"])
        candidate = _safe_relative_path(base_root, row["candidate"])
        diff = compare_visuals(baseline, candidate, row["max_diff_ratio"])
        results.append(
            {
                "id": check_id,
                "baseline": row["baseline"],
                "candidate": row["candidate"],
                **diff,
            }
        )
    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    return {
        "schema_version": 1,
        "status": overall,
        "check_count": len(results),
        "checks": results,
    }
