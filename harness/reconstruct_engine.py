"""Dreampia Native Binary/Bundle Surface Inspector & Cleanroom Reconstruction Ledger Engine.

Zero-dependency, pure Python standard-library engine for fast static inspection of
native binaries (PE, ELF, Mach-O, WASM), packaged archives (ASAR, ZIP/APK/PyZ),
source/bundle surfaces (JS/TS/Python exports, API routes, IPC channels), and
fail-closed Cleanroom Reconstruction Obligation Ledgers.

SOLID Architecture:
- BinaryArtifactInspector: Single responsibility for deterministic binary/archive header & section parsing
- SurfaceExtractor: Single responsibility for extracting symbols, routes, and IPC contracts from code/bundles
- SurfaceComparator: Single responsibility for comparing reference vs reconstructed surface parity
- ObligationLedgerEngine: Single responsibility for cleanroom obligation derivation and fail-closed coverage closure
- ExternalToolBridge: Dependency-inverted optional adapter for host disassemblers (objdump, nm, strings)
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import zipfile

try:
    from . import process as _proc, write_boundary
except ImportError:
    import process as _proc  # type: ignore[no-redef]
    import write_boundary  # type: ignore[no-redef]

ENGINE_VERSION = "1.0.0"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_STRINGS_COUNT = 200

_ASCII_STR_RE = re.compile(rb"[\x20-\x7e]{5,120}")
_DLL_NAME_RE = re.compile(r"(?i)\b[A-Za-z0-9_.-]+\.dll\b")

# Surface extraction patterns for JS/TS/Python/Web bundles
_JS_EXPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bexport\s+(?:async\s+)?(?:function|class|const|let|var|interface|type)\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
    re.compile(r"\bexport\s*\{\s*([^}]+)\}"),
    re.compile(r"\bmodule\.exports\.([A-Za-z_$][A-Za-z0-9_$]*)\s*="),
    re.compile(r"\bexports\.([A-Za-z_$][A-Za-z0-9_$]*)\s*="),
)
_PY_EXPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?:async\s+)?def\s+([A-Za-z][A-Za-z0-9_]*)\s*\(", re.MULTILINE),
    re.compile(r"^class\s+([A-Za-z][A-Za-z0-9_]*)\s*[\(:]", re.MULTILINE),
)
_ROUTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""['"](/api/[A-Za-z0-9_./:{}-]+|/v[1-9]/[A-Za-z0-9_./:{}-]+)['"]"""),
    re.compile(r"""\b(?:app|router)\.(?:get|post|put|delete|patch)\(\s*['"]([^'"]+)['"]"""),
)
_IPC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"""\bipc(?:Main|Renderer)\.(?:handle|on|invoke|send)\(\s*['"]([^'"]+)['"]"""),
)

_ELF_MACHINES: dict[int, str] = {
    0x03: "EM_386",
    0x28: "EM_ARM",
    0x3E: "EM_X86_64",
    0xB7: "EM_AARCH64",
    0xF3: "EM_RISCV",
}
_ELF_TYPES: dict[int, str] = {
    1: "ET_REL",
    2: "ET_EXEC",
    3: "ET_DYN",
    4: "ET_CORE",
}
_PE_MACHINES: dict[int, str] = {
    0x014C: "IMAGE_FILE_MACHINE_I386",
    0x8664: "IMAGE_FILE_MACHINE_AMD64",
    0xAA64: "IMAGE_FILE_MACHINE_ARM64",
}
_WASM_SECTIONS: dict[int, str] = {
    0: "custom",
    1: "type",
    2: "import",
    3: "function",
    4: "table",
    5: "memory",
    6: "global",
    7: "export",
    8: "start",
    9: "element",
    10: "code",
    11: "data",
    12: "data_count",
}


class ReconstructError(ValueError):
    """역설계 분석 및 재구축 검증 중 발생하는 도메인 예외."""

    code = "RECONSTRUCT_INVALID"


@dataclass(frozen=True)
class ObligationItem:
    """클린룸 재구축 의무 항목(Obligation) 데이터 모델."""

    obligation_id: str
    category: str
    symbol_or_contract: str
    source_location: str
    evidence_digest: str
    documented_in_spec: bool
    implemented_in_target: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "obligation_id": self.obligation_id,
            "category": self.category,
            "symbol_or_contract": self.symbol_or_contract,
            "source_location": self.source_location,
            "evidence_digest": self.evidence_digest,
            "documented_in_spec": self.documented_in_spec,
            "implemented_in_target": self.implemented_in_target,
            "status": (
                "VERIFIED"
                if self.documented_in_spec and self.implemented_in_target
                else "SPEC_ONLY"
                if self.documented_in_spec
                else "UNMAPPED"
            ),
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_project_path(root: Path, rel_path: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip() or "\\" in rel_path or "\x00" in rel_path:
        raise ReconstructError(f"유효하지 않은 상대 경로입니다: {rel_path}")
    pure = PurePosixPath(rel_path.strip())
    if pure.is_absolute() or any(part in ("", "..") for part in pure.parts):
        raise ReconstructError(f"프로젝트 루트 외부 경로는 허용되지 않습니다: {rel_path}")
    resolved_root = root.resolve()
    cur = resolved_root
    for part in pure.parts:
        if part == ".":
            continue
        cur = cur / part
        if cur.is_symlink():
            raise ReconstructError(f"심볼릭 링크 경로는 허용되지 않습니다: {rel_path}")
    return cur


def _extract_printable_strings(data: bytes, limit: int = MAX_STRINGS_COUNT) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _ASCII_STR_RE.finditer(data[: 2 * 1024 * 1024]):
        text = match.group(0).decode("ascii", errors="ignore").strip()
        if len(text) >= 5 and text not in seen:
            seen.add(text)
            found.append(text)
            if len(found) >= limit:
                break
    return found


def _read_leb128_u32(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    pos = offset
    while pos < len(data) and shift < 35:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, pos
        shift += 7
    raise ReconstructError("손상된 LEB128 인코딩입니다.")


def _parse_pe_header(data: bytes) -> dict[str, object]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ReconstructError("유효한 PE(MZ) 헤더가 아닙니다.")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        raise ReconstructError("유효한 PE 시그니처가 아닙니다.")
    machine, num_sections, timestamp, _, _, opt_size, characteristics = struct.unpack_from(
        "<HHIIIHH", data, pe_offset + 4
    )
    opt_offset = pe_offset + 24
    bits = 32
    entry_point = 0
    image_base = 0
    if opt_size >= 24 and opt_offset + opt_size <= len(data):
        magic = struct.unpack_from("<H", data, opt_offset)[0]
        entry_point = struct.unpack_from("<I", data, opt_offset + 16)[0]
        if magic == 0x20B and opt_size >= 32:
            bits = 64
            image_base = struct.unpack_from("<Q", data, opt_offset + 24)[0]
        elif magic == 0x10B and opt_size >= 32:
            bits = 32
            image_base = struct.unpack_from("<I", data, opt_offset + 28)[0]

    sec_table_offset = opt_offset + opt_size
    sections: list[dict[str, object]] = []
    for idx in range(min(num_sections, 64)):
        soff = sec_table_offset + idx * 40
        if soff + 40 > len(data):
            break
        raw_name, virt_size, virt_addr, raw_size, raw_ptr, _, _, _, _, sec_flags = struct.unpack_from(
            "<8sIIIIIIHHI", data, soff
        )
        sec_name = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace")
        sections.append(
            {
                "index": idx,
                "name": sec_name,
                "virtual_address": hex(virt_addr),
                "virtual_size": hex(virt_size),
                "raw_offset": hex(raw_ptr),
                "raw_size": hex(raw_size),
                "flags": hex(sec_flags),
                "executable": bool(sec_flags & 0x20000000),
            }
        )

    strings = _extract_printable_strings(data)
    dll_imports = sorted({m.group(0).lower() for s in strings for m in _DLL_NAME_RE.finditer(s)})
    return {
        "format": "pe",
        "architecture": {
            "machine": _PE_MACHINES.get(machine, hex(machine)),
            "bits": bits,
            "byte_order": "little",
        },
        "entry_point": hex(entry_point),
        "image_base": hex(image_base),
        "timestamp": timestamp,
        "is_dll": bool(characteristics & 0x2000),
        "sections": sections,
        "imported_modules": dll_imports,
        "strings_sample": strings[:40],
    }


def _parse_elf_header(data: bytes) -> dict[str, object]:
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise ReconstructError("유효한 ELF 헤더가 아닙니다.")
    ei_class = data[4]
    ei_data = data[5]
    bits = 64 if ei_class == 2 else 32
    endian = "<" if ei_data == 1 else ">"
    byte_order = "little" if ei_data == 1 else "big"

    if bits == 64:
        if len(data) < 64:
            raise ReconstructError("ELF64 헤더 길이가 부족합니다.")
        e_type, e_machine, _, e_entry, e_phoff, e_shoff, _, _, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = (
            struct.unpack_from(endian + "HHIQQQIHHHHHH", data, 16)
        )
    else:
        e_type, e_machine, _, e_entry, e_phoff, e_shoff, _, _, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx = (
            struct.unpack_from(endian + "HHIIIIIHHHHHH", data, 16)
        )

    segments: list[dict[str, object]] = []
    if e_phoff and e_phentsize and e_phnum:
        for idx in range(min(e_phnum, 64)):
            poff = e_phoff + idx * e_phentsize
            if poff + e_phentsize > len(data):
                break
            if bits == 64 and e_phentsize >= 56:
                p_type, p_flags, p_offset, p_vaddr, _, p_filesz, p_memsz, _ = struct.unpack_from(
                    endian + "IIQQQQQQ", data, poff
                )
            elif bits == 32 and e_phentsize >= 32:
                p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, p_flags, _ = struct.unpack_from(
                    endian + "IIIIIIII", data, poff
                )
            else:
                break
            segments.append(
                {
                    "index": idx,
                    "type": p_type,
                    "offset": hex(p_offset),
                    "virtual_address": hex(p_vaddr),
                    "file_size": hex(p_filesz),
                    "memory_size": hex(p_memsz),
                    "permissions": {
                        "read": bool(p_flags & 4),
                        "write": bool(p_flags & 2),
                        "execute": bool(p_flags & 1),
                    },
                }
            )

    raw_sections: list[tuple[int, int, int, int, int, int]] = []
    if e_shoff and e_shentsize and e_shnum:
        for idx in range(min(e_shnum, 128)):
            soff = e_shoff + idx * e_shentsize
            if soff + e_shentsize > len(data):
                break
            if bits == 64 and e_shentsize >= 64:
                sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size = struct.unpack_from(
                    endian + "IIQQQQ", data, soff
                )
            elif bits == 32 and e_shentsize >= 40:
                sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size = struct.unpack_from(
                    endian + "IIIIII", data, soff
                )
            else:
                break
            raw_sections.append((sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size))

    shstrtab = b""
    if 0 <= e_shstrndx < len(raw_sections):
        _, _, _, _, str_off, str_sz = raw_sections[e_shstrndx]
        if str_off + str_sz <= len(data):
            shstrtab = data[str_off : str_off + str_sz]

    sections: list[dict[str, object]] = []
    for idx, (sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size) in enumerate(raw_sections):
        sec_label = ""
        if shstrtab and sh_name < len(shstrtab):
            sec_label = shstrtab[sh_name:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        sections.append(
            {
                "index": idx,
                "name": sec_label,
                "type": sh_type,
                "address": hex(sh_addr),
                "offset": hex(sh_offset),
                "size": hex(sh_size),
                "flags": hex(sh_flags),
            }
        )

    strings = _extract_printable_strings(data)
    return {
        "format": "elf",
        "architecture": {
            "machine": _ELF_MACHINES.get(e_machine, hex(e_machine)),
            "bits": bits,
            "byte_order": byte_order,
        },
        "image_type": _ELF_TYPES.get(e_type, hex(e_type)),
        "entry_point": hex(e_entry),
        "segments": segments,
        "sections": sections,
        "strings_sample": strings[:40],
    }


def _parse_macho_header(data: bytes) -> dict[str, object]:
    if len(data) < 28:
        raise ReconstructError("유효한 Mach-O 헤더가 아닙니다.")
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic == 0xCAFEBABE:
        nfat_arch = struct.unpack_from(">I", data, 4)[0]
        return {
            "format": "macho-universal",
            "architecture": {"machine": "universal", "bits": 64, "byte_order": "big"},
            "fat_slices": nfat_arch,
            "strings_sample": _extract_printable_strings(data)[:40],
        }
    le_magic = struct.unpack_from("<I", data, 0)[0]
    bits = 64 if le_magic in (0xFEEDFACF, 0xCFFAEDFE) else 32
    endian = "<" if le_magic in (0xFEEDFACE, 0xFEEDFACF) else ">"
    _, cputype, _, filetype, ncmds, sizeofcmds, flags = struct.unpack_from(endian + "IIIIIII", data, 0)
    cpu_name = "ARM64" if (cputype & 0xFF) == 12 and (cputype & 0x01000000) else "X86_64" if (cputype & 0xFF) == 7 else hex(cputype)
    return {
        "format": "macho",
        "architecture": {
            "machine": cpu_name,
            "bits": bits,
            "byte_order": "little" if endian == "<" else "big",
        },
        "filetype": filetype,
        "load_commands": ncmds,
        "sizeofcmds": sizeofcmds,
        "flags": hex(flags),
        "strings_sample": _extract_printable_strings(data)[:40],
    }


def _parse_wasm_module(data: bytes) -> dict[str, object]:
    if len(data) < 8 or data[:4] != b"\x00asm":
        raise ReconstructError("유효한 WebAssembly 바이너리가 아닙니다.")
    version = struct.unpack_from("<I", data, 4)[0]
    pos = 8
    sections: list[dict[str, object]] = []
    exports: list[dict[str, str]] = []
    imports: list[dict[str, str]] = []

    while pos < len(data):
        sec_id = data[pos]
        pos += 1
        sec_size, pos = _read_leb128_u32(data, pos)
        sec_end = min(len(data), pos + sec_size)
        sec_name = _WASM_SECTIONS.get(sec_id, f"unknown_{sec_id}")
        sections.append({"id": sec_id, "name": sec_name, "offset": hex(pos), "size": sec_size})

        if sec_id == 2 and pos < sec_end:
            try:
                count, cur = _read_leb128_u32(data, pos)
                for _ in range(min(count, 128)):
                    mod_len, cur = _read_leb128_u32(data, cur)
                    mod_name = data[cur : cur + mod_len].decode("utf-8", errors="replace")
                    cur += mod_len
                    fld_len, cur = _read_leb128_u32(data, cur)
                    fld_name = data[cur : cur + fld_len].decode("utf-8", errors="replace")
                    cur += fld_len
                    kind = data[cur]
                    cur += 1
                    if kind == 0:
                        _, cur = _read_leb128_u32(data, cur)
                    imports.append({"module": mod_name, "field": fld_name, "kind": str(kind)})
            except (IndexError, ReconstructError):
                pass
        elif sec_id == 7 and pos < sec_end:
            try:
                count, cur = _read_leb128_u32(data, pos)
                kind_map = {0: "func", 1: "table", 2: "memory", 3: "global"}
                for _ in range(min(count, 256)):
                    name_len, cur = _read_leb128_u32(data, cur)
                    exp_name = data[cur : cur + name_len].decode("utf-8", errors="replace")
                    cur += name_len
                    kind = data[cur]
                    cur += 1
                    idx_val, cur = _read_leb128_u32(data, cur)
                    exports.append({"name": exp_name, "kind": kind_map.get(kind, str(kind)), "index": str(idx_val)})
            except (IndexError, ReconstructError):
                pass
        pos = sec_end

    return {
        "format": "wasm",
        "version": version,
        "sections": sections,
        "imports": imports,
        "exports": exports,
    }


def _parse_asar_archive(data: bytes) -> dict[str, object]:
    if len(data) < 16:
        raise ReconstructError("유효한 ASAR 아카이브가 아닙니다.")
    _, header_size, _, json_size = struct.unpack_from("<IIII", data, 0)
    if 16 + json_size > len(data):
        raise ReconstructError("ASAR 헤더 크기가 파일 범위를 초과합니다.")
    raw_json = data[16 : 16 + json_size].rstrip(b"\x00")
    tree = json.loads(raw_json.decode("utf-8"))
    entries: list[str] = []

    def _walk_asar(node: dict[str, object], prefix: str) -> None:
        files_obj = node.get("files")
        if isinstance(files_obj, dict):
            for name, child in sorted(files_obj.items()):
                rel = f"{prefix}/{name}" if prefix else str(name)
                if isinstance(child, dict):
                    if "files" in child:
                        _walk_asar(child, rel)
                    else:
                        entries.append(rel)

    if isinstance(tree, dict):
        _walk_asar(tree, "")
    return {
        "format": "asar",
        "header_size": header_size,
        "files_count": len(entries),
        "entries": entries[:200],
    }


def extract_code_surface(text: str, language_hint: str = "") -> dict[str, list[str]]:
    """소스 코드 또는 번들 텍스트에서 공개 심볼, 라우트, IPC 채널을 결정론적으로 추출한다."""
    exports: set[str] = set()
    routes: set[str] = set()
    ipc_channels: set[str] = set()

    if language_hint in ("py", ".py"):
        for pat in _PY_EXPORT_PATTERNS:
            for match in pat.finditer(text):
                sym = match.group(1).strip()
                if not sym.startswith("_"):
                    exports.add(sym)
    else:
        for pat in _JS_EXPORT_PATTERNS:
            for match in pat.finditer(text):
                raw = match.group(1)
                for part in raw.split(","):
                    cleaned = part.strip().split(" as ")[-1].strip()
                    if cleaned and re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", cleaned):
                        exports.add(cleaned)
        for pat in _PY_EXPORT_PATTERNS:
            for match in pat.finditer(text):
                sym = match.group(1).strip()
                if not sym.startswith("_"):
                    exports.add(sym)

    for pat in _ROUTE_PATTERNS:
        for match in pat.finditer(text):
            routes.add(match.group(1).strip())

    for pat in _IPC_PATTERNS:
        for match in pat.finditer(text):
            ipc_channels.add(match.group(1).strip())

    return {
        "exports": sorted(exports),
        "routes": sorted(routes),
        "ipc_channels": sorted(ipc_channels),
    }


OPTIONAL_RE_TOOLS: tuple[dict[str, object], ...] = (
    {
        "id": "objdump",
        "binaries": ("llvm-objdump", "objdump"),
        "formats": ("pe", "elf", "macho"),
        "purpose_ko": "PE/ELF/Mach-O 네이티브 바이너리 디스어셈블리 및 동적 심볼 테이블 정밀 추출",
        "install_cmd": {
            "windows": "winget install -e --id LLVM.LLVM",
            "macos": "brew install llvm",
            "linux": "sudo apt-get install -y binutils llvm",
        },
    },
    {
        "id": "nm",
        "binaries": ("llvm-nm", "nm"),
        "formats": ("pe", "elf", "macho"),
        "purpose_ko": "네이티브 목적 파일 및 공유 라이브러리의 공개 심볼(Export Symbol) 목록 고속 추출",
        "install_cmd": {
            "windows": "winget install -e --id LLVM.LLVM",
            "macos": "xcode-select --install",
            "linux": "sudo apt-get install -y binutils",
        },
    },
    {
        "id": "rizin",
        "binaries": ("rizin", "rz-bin"),
        "formats": ("pe", "elf", "macho", "wasm"),
        "purpose_ko": "다중 아키텍처 바이너리 함수 제어 흐름(CFG), 문자열, 크로스레퍼런스(Xref) 심층 분석",
        "install_cmd": {
            "windows": "winget install -e --id Rizin.Rizin",
            "macos": "brew install rizin",
            "linux": "sudo apt-get install -y rizin",
        },
    },
    {
        "id": "jadx",
        "binaries": ("jadx",),
        "formats": ("apk",),
        "purpose_ko": "Android APK 및 DEX 바이트코드의 Java/Kotlin 클래스·메서드 시그니처 디컴파일",
        "install_cmd": {
            "windows": "winget install -e --id skylot.jadx",
            "macos": "brew install jadx",
            "linux": "sudo apt-get install -y jadx",
        },
    },
    {
        "id": "wasm2wat",
        "binaries": ("wasm2wat", "wasm-objdump"),
        "formats": ("wasm",),
        "purpose_ko": "WebAssembly(.wasm) 바이너리를 WAT 텍스트 표현식 및 함수 시그니처로 역변환",
        "install_cmd": {
            "windows": "winget install -e --id WebAssembly.wabt",
            "macos": "brew install wabt",
            "linux": "sudo apt-get install -y wabt",
        },
    },
    {
        "id": "ghidra",
        "binaries": ("analyzeHeadless", "analyzeHeadless.bat"),
        "formats": ("pe", "elf", "macho"),
        "purpose_ko": "NSA Ghidra 헤드리스 디컴파일러 기반 네이티브 기계어 C 의사코드(Pseudocode) 복원",
        "install_cmd": {
            "windows": "winget install -e --id NSA.Ghidra",
            "macos": "brew install --cask ghidra",
            "linux": "sudo snap install ghidra",
        },
    },
    {
        "id": "adb",
        "binaries": ("adb",),
        "formats": ("apk",),
        "purpose_ko": "Android 기기/에뮬레이터 패키지 추출 및 런타임 로그/서비스 상태 점검",
        "install_cmd": {
            "windows": "winget install -e --id Google.PlatformTools",
            "macos": "brew install android-platform-tools",
            "linux": "sudo apt-get install -y adb",
        },
    },
)


def _detect_os_key() -> str:
    import sys
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def detect_package_managers() -> dict[str, str | None]:
    """호스트 OS에서 사용 가능한 패키지 매니저(winget, scoop, choco, brew, apt-get, npm) 경로를 탐색한다."""
    managers = ("winget", "scoop", "choco", "brew", "apt-get", "npm")
    return {name: _proc.fast_which(name) for name in managers}


def _infer_package_manager_from_cmd(cmd: str) -> str:
    stripped = cmd.strip()
    if stripped.startswith("winget "):
        return "winget"
    if stripped.startswith("scoop "):
        return "scoop"
    if stripped.startswith("choco "):
        return "choco"
    if stripped.startswith("brew "):
        return "brew"
    if "apt-get " in stripped:
        return "apt-get"
    if stripped.startswith("npm "):
        return "npm"
    return "manual"


def probe_optional_external_tools() -> dict[str, str | None]:
    """호스트에 선택적으로 설치된 네이티브 역공학 보조 도구(objdump, nm, rizin, jadx, wasm2wat, ghidra, adb) 가용성을 탐색한다."""
    tools = ("objdump", "llvm-objdump", "nm", "llvm-nm", "strings", "rizin", "rz-bin", "jadx", "wasm2wat", "analyzeHeadless", "adb")
    return {name: _proc.fast_which(name) for name in tools}



def reconstruct_doctor(
    install_tool: str | None = None,
    apply: bool = False,
) -> dict[str, object]:
    """2-Tier 클린룸 역공학 진단기: Tier 1(내장 무의존성 엔진) 및 Tier 2(선택적 외부 전문 리버싱 도구) 설치 상태, 패키지 매니저 가용성, 선택적 자동 설치 계획/실행 결과를 반환한다."""
    import os
    import shlex
    import subprocess

    os_key = _detect_os_key()
    pkg_managers = detect_package_managers()
    available_pkg_managers = [k for k, v in pkg_managers.items() if v is not None]
    tool_rows: list[dict[str, object]] = []
    install_commands: list[str] = []
    available_count = 0

    for spec in OPTIONAL_RE_TOOLS:
        tool_id = str(spec["id"])
        binaries = spec["binaries"]  # type: ignore[assignment]
        resolved: str | None = None
        matched_bin: str | None = None
        for b in binaries:  # type: ignore[union-attr]
            found = _proc.fast_which(str(b))
            if found:
                resolved = found
                matched_bin = str(b)
                break
        installed = resolved is not None
        if installed:
            available_count += 1
        cmd_map = spec["install_cmd"]  # type: ignore[assignment]
        install_hint = str(cmd_map.get(os_key, "")) if isinstance(cmd_map, dict) else ""
        pkg_mgr = _infer_package_manager_from_cmd(install_hint)
        pkg_mgr_ready = pkg_managers.get(pkg_mgr) is not None
        if not installed and install_hint and install_hint not in install_commands:
            install_commands.append(install_hint)

        tool_rows.append(
            {
                "id": tool_id,
                "installed": installed,
                "binary": matched_bin,
                "resolved_path": resolved,
                "supported_formats": list(spec["formats"]),  # type: ignore[arg-type]
                "purpose_ko": str(spec["purpose_ko"]),
                "install_command": install_hint,
                "package_manager": pkg_mgr,
                "package_manager_ready": pkg_mgr_ready,
            }
        )

    result: dict[str, object] = {
        "engine_version": ENGINE_VERSION,
        "os_platform": os_key,
        "tier1_builtin_engine": {
            "status": "READY",
            "zero_dependency": True,
            "supported_formats": ["pe", "elf", "macho", "wasm", "asar", "apk", "zip", "source"],
            "message_ko": "Tier 1 내장 정적 역공학 엔진은 외부 프로그램 없이 100% 즉시 작동합니다.",
        },
        "tier2_external_booster": {
            "booster_active": available_count > 0,
            "available_count": available_count,
            "total_catalog_count": len(OPTIONAL_RE_TOOLS),
            "detected_package_managers": pkg_managers,
            "available_package_managers": available_pkg_managers,
            "tools": tool_rows,
            "recommended_install_commands": install_commands,
            "message_ko": (
                f"Tier 2 외부 리버싱 부스터 도구 {available_count}/{len(OPTIONAL_RE_TOOLS)}개가 활성화되어 심층 심볼 추출을 자동 병합합니다."
                if available_count > 0
                else "현재 Tier 1(내장 무의존성 모드)로 동작 중입니다. 심층 디컴파일이 필요하면 recommended_install_commands 또는 --install-tool 옵션으로 선택 설치하십시오."
            ),
        },
        "status": "PASS",
    }

    if install_tool and install_tool.strip():
        requested_tokens = [tok.strip().lower() for tok in install_tool.split(",") if tok.strip()]
        catalog_by_id = {str(row["id"]): row for row in tool_rows}
        valid_ids = list(catalog_by_id.keys())
        if "all" in requested_tokens:
            selected_ids = valid_ids
            unknown_ids: list[str] = []
        else:
            selected_ids = [tid for tid in requested_tokens if tid in catalog_by_id]
            unknown_ids = [tid for tid in requested_tokens if tid not in catalog_by_id]

        steps: list[dict[str, object]] = []
        overall_plan_ok = len(unknown_ids) == 0

        for tid in selected_ids:
            row = catalog_by_id[tid]
            already_installed = bool(row["installed"])
            cmd = str(row["install_command"])
            pm = str(row["package_manager"])
            pm_ready = bool(row["package_manager_ready"])

            if already_installed:
                steps.append(
                    {
                        "id": tid,
                        "already_installed": True,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": False,
                        "returncode": 0,
                        "status": "SKIPPED_INSTALLED",
                        "message_ko": f"'{tid}' 도구는 이미 설치되어 있습니다 ({row['resolved_path']}).",
                    }
                )
                continue

            if not apply:
                steps.append(
                    {
                        "id": tid,
                        "already_installed": False,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": False,
                        "returncode": None,
                        "status": "PREVIEW_READY" if pm_ready else "PACKAGE_MANAGER_MISSING",
                        "message_ko": (
                            f"[미리보기] '{tid}' 설치 명령어: `{cmd}` (실제 설치하려면 --apply 옵션을 추가하십시오.)"
                            if pm_ready
                            else f"패키지 매니저('{pm}')가 시스템에 설치되어 있지 않습니다. 수동으로 `{cmd}`에 준하는 도구를 설치하십시오."
                        ),
                    }
                )
                continue

            if not pm_ready or not cmd:
                overall_plan_ok = False
                steps.append(
                    {
                        "id": tid,
                        "already_installed": False,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": False,
                        "returncode": None,
                        "status": "FAIL",
                        "message_ko": f"패키지 매니저('{pm}')를 찾을 수 없어 '{tid}' 자동 설치를 실행할 수 없습니다.",
                    }
                )
                continue

            if cmd.strip().startswith("sudo "):
                steps.append(
                    {
                        "id": tid,
                        "already_installed": False,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": False,
                        "returncode": None,
                        "status": "MANUAL_SUDO_REQUIRED",
                        "message_ko": (
                            f"보안 정책상 관리자 권한(sudo)이 필요한 명령어(`{cmd}`)는 자동 실행하지 않습니다. "
                            "터미널에서 직접 실행하십시오."
                        ),
                    }
                )
                continue

            cmd_args = [tok.strip("\"'") for tok in shlex.split(cmd, posix=(os.name != "nt"))]
            try:
                proc = subprocess.run(
                    cmd_args,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                ok = proc.returncode == 0
                if not ok:
                    overall_plan_ok = False
                steps.append(
                    {
                        "id": tid,
                        "already_installed": False,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": True,
                        "returncode": proc.returncode,
                        "status": "INSTALLED" if ok else "FAIL",
                        "message_ko": (
                            f"'{tid}' 도구 설치 명령어가 성공적으로 완료되었습니다."
                            if ok
                            else f"'{tid}' 설치 명령어가 종료 코드 {proc.returncode}로 실패했습니다."
                        ),
                    }
                )
            except (OSError, subprocess.SubprocessError) as exc:
                overall_plan_ok = False
                steps.append(
                    {
                        "id": tid,
                        "already_installed": False,
                        "command": cmd,
                        "package_manager": pm,
                        "package_manager_ready": pm_ready,
                        "executed": True,
                        "returncode": -1,
                        "status": "FAIL",
                        "message_ko": f"'{tid}' 설치 중 예외가 발생했습니다: {exc}",
                    }
                )

        result["install_plan"] = {
            "requested_tool": install_tool,
            "applied": apply,
            "selected_ids": selected_ids,
            "unknown_ids": unknown_ids,
            "valid_catalog_ids": valid_ids,
            "steps": steps,
            "message_ko": (
                f"알 수 없는 도구 ID가 포함되어 있습니다: {', '.join(unknown_ids)} (가능한 ID: {', '.join(valid_ids)}, all)"
                if unknown_ids
                else (
                    f"Tier 2 도구({', '.join(selected_ids)}) 설치 실행이 완료되었습니다."
                    if apply
                    else f"Tier 2 도구({', '.join(selected_ids)}) 설치 계획 미리보기입니다. 실제 설치하려면 --apply를 지정하십시오."
                )
            ),
        }
        if not overall_plan_ok:
            result["status"] = "FAIL"

    return result


def run_tier2_deep_enrichment(target_path: Path, fmt: str) -> dict[str, object]:
    """설치된 Tier 2 외부 리버싱 도구가 있으면 비파괴·읽기전용(5초 타임아웃)으로 호출하여 심층 심볼을 추가 추출한다."""
    import subprocess

    discovered_symbols: set[str] = set()
    used_tool: str | None = None

    if fmt in ("pe", "elf", "macho"):
        rz_bin = shutil.which("rz-bin")
        nm_bin = shutil.which("llvm-nm") or shutil.which("nm")
        objdump_bin = shutil.which("llvm-objdump") or shutil.which("objdump")

        if rz_bin:
            try:
                proc = subprocess.run(
                    [rz_bin, "-s", str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    used_tool = "rz-bin"
                    for line in proc.stdout.splitlines()[:300]:
                        parts = line.strip().split()
                        if len(parts) >= 7 and not parts[-1].startswith(("imp.", "section.")):
                            sym = parts[-1].lstrip("_")
                            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,64}", sym):
                                discovered_symbols.add(sym)
            except (OSError, subprocess.TimeoutExpired):
                pass

        if not discovered_symbols and nm_bin:
            try:
                proc = subprocess.run(
                    [nm_bin, "-g", "--defined-only", str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    used_tool = Path(nm_bin).stem
                    for line in proc.stdout.splitlines()[:300]:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            sym = parts[-1].lstrip("_")
                            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,64}", sym):
                                discovered_symbols.add(sym)
            except (OSError, subprocess.TimeoutExpired):
                pass

        if not discovered_symbols and objdump_bin:
            try:
                proc = subprocess.run(
                    [objdump_bin, "-t", str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    used_tool = Path(objdump_bin).stem
                    for line in proc.stdout.splitlines()[:300]:
                        parts = line.strip().split()
                        if len(parts) >= 5 and ".text" in parts:
                            sym = parts[-1].lstrip("_")
                            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,64}", sym):
                                discovered_symbols.add(sym)
            except (OSError, subprocess.TimeoutExpired):
                pass

    elif fmt == "wasm":
        wasm_objdump = shutil.which("wasm-objdump")
        if wasm_objdump:
            try:
                proc = subprocess.run(
                    [wasm_objdump, "-x", str(target_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    used_tool = "wasm-objdump"
                    for match in re.finditer(r'func\[\d+\]\s+<([A-Za-z0-9_$]+)>', proc.stdout):
                        discovered_symbols.add(match.group(1))
            except (OSError, subprocess.TimeoutExpired):
                pass

    sorted_syms = sorted(discovered_symbols)[:100]
    return {
        "active": used_tool is not None,
        "tool_used": used_tool,
        "deep_symbols_count": len(sorted_syms),
        "deep_symbols": sorted_syms,
    }


def inspect_artifact(target_path: Path) -> dict[str, object]:
    """단일 바이너리/아카이브/소스 파일 또는 디렉터리의 정적 구조와 표면을 초고속으로 분석한다 (Tier 1 내장 + Tier 2 외부 부스터 자동 병합)."""
    if target_path.is_symlink() or not target_path.exists():
        raise ReconstructError(f"분석 대상이 존재하지 않거나 심볼릭 링크입니다: {target_path}")

    if target_path.is_dir():
        files_inventory: list[dict[str, object]] = []
        all_exports: set[str] = set()
        all_routes: set[str] = set()
        all_ipc: set[str] = set()
        tree_hasher = hashlib.sha256()

        for p in sorted(target_path.rglob("*")):
            if p.is_symlink() or not p.is_file():
                continue
            rel = p.relative_to(target_path).as_posix()
            if any(part in (".git", ".harness", "node_modules", "__pycache__") for part in p.parts):
                continue
            raw = p.read_bytes()
            f_sha = _sha256_bytes(raw)
            tree_hasher.update(rel.encode("utf-8") + b"\x00" + f_sha.encode("ascii") + b"\x00")
            entry_info: dict[str, object] = {"path": rel, "bytes": len(raw), "sha256": f_sha}
            if p.suffix.lower() in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".py"):
                surf = extract_code_surface(raw.decode("utf-8", errors="replace"), p.suffix.lower())
                all_exports.update(surf["exports"])
                all_routes.update(surf["routes"])
                all_ipc.update(surf["ipc_channels"])
                entry_info["surface"] = surf
            files_inventory.append(entry_info)

        return {
            "engine_version": ENGINE_VERSION,
            "kind": "directory",
            "path": str(target_path.resolve()),
            "sha256": tree_hasher.hexdigest(),
            "files_count": len(files_inventory),
            "files": files_inventory[:200],
            "surface": {
                "exports": sorted(all_exports),
                "routes": sorted(all_routes),
                "ipc_channels": sorted(all_ipc),
            },
        }

    size = target_path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ReconstructError(f"아티팩트 크기가 최대 한도(64MiB)를 초과합니다: {size}")
    data = target_path.read_bytes()
    sha256 = _sha256_bytes(data)

    base_meta: dict[str, object] = {
        "engine_version": ENGINE_VERSION,
        "path": str(target_path.resolve()),
        "bytes": len(data),
        "sha256": sha256,
    }

    if data.startswith(b"MZ"):
        parsed = _parse_pe_header(data)
        return {**base_meta, **parsed, "tier2_enrichment": run_tier2_deep_enrichment(target_path, "pe")}
    if data.startswith(b"\x7fELF"):
        parsed = _parse_elf_header(data)
        return {**base_meta, **parsed, "tier2_enrichment": run_tier2_deep_enrichment(target_path, "elf")}
    if len(data) >= 4 and struct.unpack_from(">I", data, 0)[0] in (
        0xFEEDFACE,
        0xCEFAEDFE,
        0xFEEDFACF,
        0xCFFAEDFE,
        0xCAFEBABE,
    ):
        parsed = _parse_macho_header(data)
        return {**base_meta, **parsed, "tier2_enrichment": run_tier2_deep_enrichment(target_path, "macho")}
    if data.startswith(b"\x00asm"):
        parsed = _parse_wasm_module(data)
        return {**base_meta, **parsed, "tier2_enrichment": run_tier2_deep_enrichment(target_path, "wasm")}
    if target_path.suffix.lower() == ".asar" or (
        len(data) >= 16 and struct.unpack_from("<I", data, 0)[0] == 4 and data[16:17] == b"{"
    ):
        return {**base_meta, **_parse_asar_archive(data)}
    if zipfile.is_zipfile(target_path):
        with zipfile.ZipFile(target_path, "r") as zf:
            names = sorted(zf.namelist())
            has_dex = "classes.dex" in names
            has_manifest = "AndroidManifest.xml" in names
            fmt = "apk" if (has_dex and has_manifest) else "zip"
            return {
                **base_meta,
                "format": fmt,
                "entries_count": len(names),
                "entries": names[:200],
                "android_apk": has_dex and has_manifest,
                "tier2_enrichment": run_tier2_deep_enrichment(target_path, fmt),
            }

    text = data.decode("utf-8", errors="replace")
    surf = extract_code_surface(text, target_path.suffix.lower())
    return {
        **base_meta,
        "format": "source",
        "surface": surf,
        "strings_sample": _extract_printable_strings(data)[:40],
    }


def compare_surfaces(reference_path: Path, target_path: Path) -> dict[str, object]:
    """참조 아티팩트(원본 바이너리/번들/소스)와 재구축 대상(구현체) 간의 표면 일치율을 계산한다."""
    ref_info = inspect_artifact(reference_path)
    tgt_info = inspect_artifact(target_path)

    def _collect_tokens(info: dict[str, object]) -> tuple[set[str], set[str], set[str]]:
        surf = info.get("surface")
        exports: set[str] = set()
        routes: set[str] = set()
        ipc: set[str] = set()
        if isinstance(surf, dict):
            exports.update(str(x) for x in (surf.get("exports") or []) if isinstance(surf.get("exports"), list))
            routes.update(str(x) for x in (surf.get("routes") or []) if isinstance(surf.get("routes"), list))
            ipc.update(str(x) for x in (surf.get("ipc_channels") or []) if isinstance(surf.get("ipc_channels"), list))
        if info.get("format") == "wasm" and isinstance(info.get("exports"), list):
            for item in info["exports"]:  # type: ignore[index]
                if isinstance(item, dict) and "name" in item:
                    exports.add(str(item["name"]))
        return exports, routes, ipc

    ref_exp, ref_routes, ref_ipc = _collect_tokens(ref_info)
    tgt_exp, tgt_routes, tgt_ipc = _collect_tokens(tgt_info)

    ref_all = {f"export:{x}" for x in ref_exp} | {f"route:{x}" for x in ref_routes} | {f"ipc:{x}" for x in ref_ipc}
    tgt_all = {f"export:{x}" for x in tgt_exp} | {f"route:{x}" for x in tgt_routes} | {f"ipc:{x}" for x in tgt_ipc}

    matched = sorted(ref_all & tgt_all)
    missing = sorted(ref_all - tgt_all)
    added = sorted(tgt_all - ref_all)
    parity_ratio = round(len(matched) / len(ref_all), 4) if ref_all else 1.0

    return {
        "reference_sha256": ref_info.get("sha256"),
        "target_sha256": tgt_info.get("sha256"),
        "reference_count": len(ref_all),
        "target_count": len(tgt_all),
        "matched_count": len(matched),
        "missing_count": len(missing),
        "added_count": len(added),
        "parity_ratio": parity_ratio,
        "matched": matched,
        "missing": missing,
        "added": added,
        "status": "PASS" if not missing else "INCOMPLETE",
    }


def build_obligation_ledger(
    root: Path,
    reference_rel: str,
    *,
    spec_rel: str = "approved-spec",
    target_rel: str = "implementation",
) -> dict[str, object]:
    """참조 아티팩트에서 재구축 의무 항목(Obligation Ledger)을 도출하고 명세·구현 매핑 상태를 기록한다."""
    ref_path = _safe_project_path(root, reference_rel)
    ref_info = inspect_artifact(ref_path)

    spec_text = ""
    spec_path = _safe_project_path(root, spec_rel)
    if spec_path.exists():
        if spec_path.is_file():
            spec_text = spec_path.read_text(encoding="utf-8", errors="replace")
        elif spec_path.is_dir():
            parts: list[str] = []
            for p in sorted(spec_path.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    parts.append(p.read_text(encoding="utf-8", errors="replace"))
            spec_text = "\n".join(parts)

    target_symbols: set[str] = set()
    target_routes: set[str] = set()
    target_ipc: set[str] = set()
    target_text = ""
    target_path = _safe_project_path(root, target_rel)
    if target_path.exists():
        tgt_info = inspect_artifact(target_path)
        surf = tgt_info.get("surface")
        if isinstance(surf, dict):
            target_symbols.update(str(x) for x in (surf.get("exports") or []) if isinstance(surf.get("exports"), list))
            target_routes.update(str(x) for x in (surf.get("routes") or []) if isinstance(surf.get("routes"), list))
            target_ipc.update(str(x) for x in (surf.get("ipc_channels") or []) if isinstance(surf.get("ipc_channels"), list))
        if target_path.is_file():
            target_text = target_path.read_text(encoding="utf-8", errors="replace")
        elif target_path.is_dir():
            t_parts: list[str] = []
            for p in sorted(target_path.rglob("*")):
                if p.is_file() and not p.is_symlink():
                    t_parts.append(p.read_text(encoding="utf-8", errors="replace"))
            target_text = "\n".join(t_parts)

    raw_obligations: list[tuple[str, str, str]] = []
    ref_surf = ref_info.get("surface")
    if isinstance(ref_surf, dict):
        for sym in ref_surf.get("exports") or []:  # type: ignore[union-attr]
            raw_obligations.append(("export_symbol", str(sym), reference_rel))
        for rt in ref_surf.get("routes") or []:  # type: ignore[union-attr]
            raw_obligations.append(("api_endpoint", str(rt), reference_rel))
        for ch in ref_surf.get("ipc_channels") or []:  # type: ignore[union-attr]
            raw_obligations.append(("ipc_channel", str(ch), reference_rel))

    if ref_info.get("format") == "wasm" and isinstance(ref_info.get("exports"), list):
        for exp in ref_info["exports"]:  # type: ignore[index]
            if isinstance(exp, dict) and exp.get("name"):
                raw_obligations.append(("wasm_export", str(exp["name"]), reference_rel))
    elif ref_info.get("format") in ("pe", "elf", "macho"):
        for sec in ref_info.get("sections") or []:  # type: ignore[union-attr]
            if isinstance(sec, dict) and sec.get("name"):
                raw_obligations.append(("binary_section", str(sec["name"]), reference_rel))

    items: list[dict[str, object]] = []
    for idx, (cat, token, loc) in enumerate(raw_obligations, start=1):
        obl_id = f"obl_{idx:03d}"
        ev_digest = _sha256_bytes(f"{cat}:{token}:{loc}:{ref_info.get('sha256')}".encode("utf-8"))
        in_spec = bool(token and token in spec_text)
        in_target = (
            token in target_symbols
            or token in target_routes
            or token in target_ipc
            or (bool(token) and token in target_text)
        )
        item = ObligationItem(
            obligation_id=obl_id,
            category=cat,
            symbol_or_contract=token,
            source_location=loc,
            evidence_digest=ev_digest,
            documented_in_spec=in_spec,
            implemented_in_target=in_target,
        )
        items.append(item.to_dict())

    closure_payload = json.dumps(items, sort_keys=True, separators=(",", ":")).encode("utf-8")
    closure_digest = _sha256_bytes(closure_payload)
    ledger_id = f"dp_ledger_{closure_digest[:16]}"

    return {
        "schema_version": 1,
        "engine_version": ENGINE_VERSION,
        "ledger_id": ledger_id,
        "reference_path": reference_rel,
        "reference_format": ref_info.get("format", ref_info.get("kind", "unknown")),
        "reference_sha256": ref_info.get("sha256"),
        "spec_path": spec_rel,
        "target_path": target_rel,
        "obligations_count": len(items),
        "obligations": items,
        "closure_digest": closure_digest,
    }


def evaluate_reconstruction_coverage(
    ledger: dict[str, object],
    *,
    root: Path | None = None,
    require_zero_contamination: bool = True,
) -> dict[str, object]:
    """재구축 의무 원장(Obligation Ledger)과 클린룸 오염 분리 경계를 검증하여 최종 완료 가능 여부를 판정한다."""
    obligations = ledger.get("obligations")
    if not isinstance(obligations, list):
        raise ReconstructError("유효한 obligations 목록이 필요합니다.")

    total = len(obligations)
    documented = 0
    implemented = 0
    verified = 0
    unmapped_ids: list[str] = []
    spec_only_ids: list[str] = []

    for row in obligations:
        if not isinstance(row, dict):
            continue
        oid = str(row.get("obligation_id") or "")
        doc_ok = row.get("documented_in_spec") is True
        imp_ok = row.get("implemented_in_target") is True
        if doc_ok:
            documented += 1
        if imp_ok:
            implemented += 1
        if doc_ok and imp_ok:
            verified += 1
        elif doc_ok and not imp_ok:
            spec_only_ids.append(oid)
        else:
            unmapped_ids.append(oid)

    coverage_ratio = round(verified / total, 4) if total > 0 else 1.0
    contamination_free = True
    cleanroom_detail: dict[str, object] | None = None

    if require_zero_contamination and root is not None:
        c_zone = root / "contaminated-zone"
        a_zone = root / "approved-spec"
        i_zone = root / "implementation"
        if c_zone.is_dir() and a_zone.is_dir() and i_zone.is_dir():
            cleanroom_detail = write_boundary.verify_cleanroom_separation(root)
            contamination_free = cleanroom_detail.get("status") == "PASS"

    if not contamination_free:
        closure_status = "BLOCKED_CONTAMINATION"
    elif total > 0 and verified == total:
        closure_status = "CLOSED"
    else:
        closure_status = "INCOMPLETE"

    return {
        "ledger_id": ledger.get("ledger_id"),
        "closure_digest": ledger.get("closure_digest"),
        "total_obligations": total,
        "documented_in_spec": documented,
        "implemented_in_target": implemented,
        "verified_obligations": verified,
        "coverage_ratio": coverage_ratio,
        "unmapped_obligations": unmapped_ids,
        "spec_only_obligations": spec_only_ids,
        "contamination_free": contamination_free,
        "cleanroom_check": cleanroom_detail,
        "closure_status": closure_status,
        "status": "PASS" if closure_status == "CLOSED" else "FAIL",
        "message_ko": (
            f"클린룸 재구축 의무 원장 검증 통과: {verified}/{total} 항목 완료 (커버리지 {coverage_ratio * 100:.1f}%, 무오염 확인)"
            if closure_status == "CLOSED"
            else f"클린룸 재구축 의무 원장 미완료 또는 오염 감지: 상태={closure_status} ({verified}/{total})"
        ),
    }


def generate_cleanroom_spec(
    root: Path,
    reference_rel: str = "contaminated-zone",
    *,
    spec_rel: str = "approved-spec",
    target_rel: str = "implementation",
    apply: bool = False,
) -> dict[str, object]:
    """Alchemist 클린룸 명세 자동 추출기: 참조 아티팩트(Tier 1 + Tier 2 심층 심볼)를 분석하여 오염 없는 한글 기능 명세서(approved-spec/00_CLEANROOM_SPEC.md)와 Golden I/O 템플릿을 자동 생성한다."""
    if root.is_symlink() or not root.is_dir():
        raise ReconstructError("유효하지 않은 프로젝트 루트 디렉터리입니다.")
    resolved = root.resolve()
    ref_path = _safe_project_path(resolved, reference_rel)
    if not ref_path.exists():
        raise ReconstructError(f"참조 경로가 존재하지 않습니다: {reference_rel}")

    ref_info = inspect_artifact(ref_path)
    initial_ledger = build_obligation_ledger(
        resolved,
        reference_rel,
        spec_rel=spec_rel,
        target_rel=target_rel,
    )
    obligations: list[dict[str, object]] = initial_ledger["obligations"]  # type: ignore[assignment]
    tier2_info = ref_info.get("tier2_enrichment")
    deep_symbols: list[str] = (
        list(tier2_info.get("deep_symbols", []))  # type: ignore[arg-type]
        if isinstance(tier2_info, dict) and isinstance(tier2_info.get("deep_symbols"), list)
        else []
    )
    used_booster = tier2_info.get("tool_used") if isinstance(tier2_info, dict) else None

    table_rows: list[str] = []
    export_symbols: list[str] = []
    for row in obligations:
        oid = str(row.get("obligation_id") or "")
        cat = str(row.get("category") or "export_symbol")
        sym = str(row.get("symbol_or_contract") or "")
        if cat in ("export_symbol", "wasm_export") and sym:
            export_symbols.append(sym)
        if cat == "api_endpoint":
            desc_ko = f"HTTP/API 라우트 `{sym}` 요청 수신 시 입력 스키마 검증 및 결정론적 상태 코드·JSON 응답을 반환해야 한다."
        elif cat == "ipc_channel":
            desc_ko = f"IPC 채널 `{sym}` 메시지 송수신 시 페이로드 타입 검증 및 권한 경계를 준수해야 한다."
        elif cat == "binary_section":
            desc_ko = f"바이너리 섹션 `{sym}`에 대응하는 초기화·메모리/리소스 경계를 안전하게 재구현해야 한다."
        else:
            desc_ko = f"공개 심볼 `{sym}`의 입출력 시그니처와 예외 처리 계약을 원본 코드 복사 없이 독립 구현해야 한다."
        table_rows.append(f"| `{oid}` | `{cat}` | `{sym}` | {desc_ko} |")

    if not table_rows:
        table_rows.append("| `obl_000` | `general` | `module_entry` | 아티팩트 공개 진입점 및 기본 입출력 동작 재구현 |")

    deep_section_lines: list[str] = []
    if deep_symbols:
        deep_section_lines.append(f"\n## 3. Tier 2 심층 심볼 & 호출 흐름 요약 (부스터: `{used_booster or 'auto'}`)")
        for d_sym in deep_symbols[:25]:
            deep_section_lines.append(f"- `{d_sym}`: 내부 보조 심볼 또는 하위 호출 후보 (클린룸 블랙박스 참조용)")
    else:
        deep_section_lines.append("\n## 3. Tier 2 심층 심볼 & 호출 흐름 요약")
        deep_section_lines.append("- Tier 1 내장 정적 파서 기준으로 표면 추출 완료 (심층 디스어셈블리가 필요하면 `reconstruct-doctor --install-tool rizin,jadx` 활용)")

    spec_md = (
        "# 00. 클린룸 블랙박스 기능 명세서 (Approved Cleanroom Specification)\n\n"
        "- 클린룸 무오염 원칙: 본 명세서는 contaminated-zone의 원본 구현 코드를 복사하지 않고, "
        "관찰 가능한 공개 심볼, API 라우트, IPC 채널 및 입출력 계약만을 한글로 기술한 승인 명세서입니다.\n\n"
        "## 1. 참조 아티팩트 메타데이터\n"
        f"- 참조 경로: {reference_rel}\n"
        f"- 아티팩트 포맷: {initial_ledger.get('reference_format')}\n"
        f"- 참조 SHA-256: {initial_ledger.get('reference_sha256')}\n"
        f"- 총 재구축 의무 항목 수: {len(obligations)}\n\n"
        "## 2. 재구축 의무 계약표 (Obligation Contracts)\n\n"
        "| 의무 ID | 분류 | 심볼 / 계약 토큰 | 블랙박스 동작 요구사항 (한글 명세) |\n"
        "| :--- | :--- | :--- | :--- |\n"
        + "\n".join(table_rows)
        + "\n"
        + "\n".join(deep_section_lines)
        + "\n"
    )

    spec_dir = _safe_project_path(resolved, spec_rel)
    spec_file_rel = f"{spec_rel.rstrip('/')}/00_CLEANROOM_SPEC.md"
    golden_file_rel = f"{spec_rel.rstrip('/')}/golden-io.json"
    ledger_file_rel = "evidence/reconstruction-ledger.json"

    first_fn = export_symbols[0] if export_symbols else "reconstructed_entry"
    golden_template: dict[str, object] = {
        "schema_version": 1,
        "template_only": True,
        "module_path": f"{target_rel.rstrip('/')}/reconstructed_service.py",
        "cases": [
            {
                "id": "golden_case_001",
                "function": first_fn,
                "args": ["valid-input"],
                "kwargs": {},
                "expected": True,
            }
        ],
    }

    updated_files: list[str] = []
    final_ledger = initial_ledger
    if apply:
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file_path = resolved / spec_file_rel
        spec_file_path.write_text(spec_md, encoding="utf-8")
        updated_files.append(spec_file_rel)

        golden_file_path = resolved / golden_file_rel
        if not golden_file_path.is_file():
            golden_file_path.write_text(
                json.dumps(golden_template, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            updated_files.append(golden_file_rel)

        final_ledger = build_obligation_ledger(
            resolved,
            reference_rel,
            spec_rel=spec_rel,
            target_rel=target_rel,
        )
        ledger_path = resolved / ledger_file_rel
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(
            json.dumps(final_ledger, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        updated_files.append(ledger_file_rel)

    return {
        "action": "reconstruct-spec",
        "status": "PASS",
        "applied": apply,
        "reference_path": reference_rel,
        "spec_file": spec_file_rel,
        "golden_io_file": golden_file_rel,
        "obligations_count": len(obligations),
        "deep_symbols_count": len(deep_symbols),
        "updated_files": updated_files,
        "ledger_id": final_ledger.get("ledger_id"),
        "spec_markdown_preview": spec_md,
        "message_ko": (
            f"클린룸 한글 명세서({spec_file_rel}) 및 의무 원장({ledger_file_rel}, 총 {len(obligations)}개 항목)이 자동 생성되었습니다."
            if apply
            else f"[미리보기] 클린룸 한글 명세서({spec_file_rel}, 의무 항목 {len(obligations)}개) 초안입니다. 실제 파일로 저장하려면 --apply를 추가하십시오."
        ),
    }

