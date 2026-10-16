import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from harness import reconstruct_engine, team_cli, universal_router


def _build_minimal_pe64() -> bytes:
    dos = bytearray(64)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 64)
    pe_sig = b"PE\x00\x00"
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x2002)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 16, 0x1000)
    struct.pack_into("<H", opt, 68, 3)
    sec = bytearray(40)
    sec[0:8] = b".text\x00\x00\x00"
    struct.pack_into("<IIII", sec, 8, 0x200, 0x1000, 0x200, 0x400)
    return bytes(dos) + pe_sig + coff + bytes(opt) + bytes(sec) + b"hello_pe_export\x00"


def _build_minimal_elf64() -> bytes:
    shstr = b"\x00.text\x00"
    shoff = 64 + len(shstr)
    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    hdr = ident + struct.pack(
        "<HHIQQQIHHHHHH",
        2,
        0x3E,
        1,
        0x401000,
        0,
        shoff,
        0,
        64,
        0,
        0,
        64,
        2,
        1,
    )
    sh_null = b"\x00" * 64
    sh_text = struct.pack(
        "<IIQQQQIIQQ",
        1,
        1,
        6,
        0x401000,
        64,
        len(shstr),
        0,
        0,
        16,
        0,
    )
    return hdr + shstr + sh_null + sh_text


def _build_minimal_macho64() -> bytes:
    cmd_size = 72
    hdr = struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, 1, cmd_size, 0, 0)
    seg = struct.pack(
        "<II16sQQQQIIII",
        0x19,
        cmd_size,
        b"__TEXT\x00" + b"\x00" * 9,
        0x100000000,
        0x4000,
        0,
        0x4000,
        7,
        5,
        0,
        0,
    )
    return hdr + seg


def _build_minimal_wasm() -> bytes:
    imp_payload = bytes([1, 3]) + b"env" + bytes([3]) + b"log" + bytes([0, 0])
    imp_sec = bytes([2, len(imp_payload)]) + imp_payload
    exp_name = b"computeScore"
    exp_payload = bytes([1, len(exp_name)]) + exp_name + bytes([0, 0])
    exp_sec = bytes([7, len(exp_name) + 4]) + exp_payload
    return b"\x00asm\x01\x00\x00\x00" + imp_sec + exp_sec


def _build_minimal_asar() -> bytes:
    tree = {
        "files": {
            "package.json": {"size": 25, "offset": "0"},
            "dist": {
                "files": {
                    "main.js": {"size": 42, "offset": "25"},
                    "native.node": {"size": 128, "unpacked": True},
                }
            },
        }
    }
    json_bytes = json.dumps(tree).encode("utf-8")
    pad = (4 - (len(json_bytes) % 4)) % 4
    padded = json_bytes + b"\x00" * pad
    header = struct.pack("<IIII", 4, 8 + len(padded), 4 + len(padded), len(json_bytes))
    return header + padded + b'{"name":"app","main":"."}'


class ReconstructEngineTests(unittest.TestCase):
    def test_inspect_pe_elf_macho_wasm_asar_apk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pe_path = root / "sample.dll"
            pe_path.write_bytes(_build_minimal_pe64())
            pe_info = reconstruct_engine.inspect_artifact(pe_path)
            self.assertEqual(pe_info["format"], "pe")
            self.assertEqual(pe_info["architecture"]["machine"], "IMAGE_FILE_MACHINE_AMD64")
            self.assertTrue(pe_info["is_dll"])
            self.assertEqual(pe_info["sections"][0]["name"], ".text")

            elf_path = root / "sample.elf"
            elf_path.write_bytes(_build_minimal_elf64())
            elf_info = reconstruct_engine.inspect_artifact(elf_path)
            self.assertEqual(elf_info["format"], "elf")
            self.assertEqual(elf_info["architecture"]["machine"], "EM_X86_64")
            self.assertIn(".text", [s["name"] for s in elf_info["sections"]])

            macho_path = root / "sample.macho"
            macho_path.write_bytes(_build_minimal_macho64())
            macho_info = reconstruct_engine.inspect_artifact(macho_path)
            self.assertEqual(macho_info["format"], "macho")
            self.assertEqual(macho_info["architecture"]["machine"], "ARM64")
            self.assertEqual(macho_info["load_commands"], 1)

            wasm_path = root / "module.wasm"
            wasm_path.write_bytes(_build_minimal_wasm())
            wasm_info = reconstruct_engine.inspect_artifact(wasm_path)
            self.assertEqual(wasm_info["format"], "wasm")
            self.assertEqual(wasm_info["imports"][0], {"module": "env", "field": "log", "kind": "0"})
            self.assertEqual(wasm_info["exports"][0]["name"], "computeScore")

            asar_path = root / "app.asar"
            asar_path.write_bytes(_build_minimal_asar())
            asar_info = reconstruct_engine.inspect_artifact(asar_path)
            self.assertEqual(asar_info["format"], "asar")
            self.assertEqual(asar_info["files_count"], 3)

            apk_path = root / "sample.apk"
            with zipfile.ZipFile(apk_path, "w") as zf:
                zf.writestr("AndroidManifest.xml", "<manifest/>")
                zf.writestr("classes.dex", "dex\n035\x00")
            apk_info = reconstruct_engine.inspect_artifact(apk_path)
            self.assertEqual(apk_info["format"], "apk")
            self.assertTrue(apk_info["android_apk"])

    def test_obligation_ledger_and_cleanroom_coverage_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            contam = proj / "contaminated-zone"
            spec_dir = proj / "approved-spec"
            impl_dir = proj / "implementation"
            contam.mkdir()
            spec_dir.mkdir()
            impl_dir.mkdir()

            (contam / "service.py").write_text(
                "def calculate_invoice(amount: int) -> int:\n"
                "    return amount * 2\n"
                "class BillingEngine:\n"
                "    pass\n",
                encoding="utf-8",
            )
            (spec_dir / "00_SPEC.md").write_text(
                "# Cleanroom Spec\n\n- Implement `calculate_invoice` and `BillingEngine`.\n",
                encoding="utf-8",
            )

            # Partial implementation -> FAIL
            (impl_dir / "rebuilt.py").write_text(
                "def calculate_invoice(total: int) -> int:\n    return total + total\n",
                encoding="utf-8",
            )
            partial_ledger = reconstruct_engine.build_obligation_ledger(proj, "contaminated-zone")
            self.assertEqual(partial_ledger["obligations_count"], 2)
            partial = reconstruct_engine.evaluate_reconstruction_coverage(
                partial_ledger,
                root=proj,
                require_zero_contamination=True,
            )
            self.assertEqual(partial["status"], "FAIL")
            self.assertEqual(partial["closure_status"], "INCOMPLETE")

            # Complete cleanroom implementation -> PASS
            (impl_dir / "rebuilt.py").write_text(
                "def calculate_invoice(total: int) -> int:\n"
                "    return total + total\n"
                "class BillingEngine:\n"
                "    def run(self) -> int:\n"
                "        return calculate_invoice(10)\n",
                encoding="utf-8",
            )
            full_ledger = reconstruct_engine.build_obligation_ledger(proj, "contaminated-zone")
            full = reconstruct_engine.evaluate_reconstruction_coverage(
                full_ledger,
                root=proj,
                require_zero_contamination=True,
            )
            self.assertEqual(full["status"], "PASS")
            self.assertEqual(full["closure_status"], "CLOSED")
            self.assertEqual(full["coverage_ratio"], 1.0)

    def test_team_cli_multi_domain_scaffolds_and_reconstruct_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "cleanroom-proj"
            proj.mkdir()
            self.assertEqual(team_cli.main(["init", "--project", str(proj), "--apply"]), 0)
            self.assertEqual(
                team_cli.main(["scaffold", "--project", str(proj), "--type", "cleanroom-reconstruct", "--apply"]),
                0,
            )
            self.assertTrue((proj / "contaminated-zone" / "README.md").is_file())
            self.assertTrue((proj / "approved-spec" / "00_CLEANROOM_SPEC.md").is_file())
            self.assertTrue((proj / "implementation" / "README.md").is_file())

            (proj / "contaminated-zone" / "legacy.ts").write_text(
                "export function verifyToken(token: string): boolean { return Boolean(token); }\n",
                encoding="utf-8",
            )
            (proj / "approved-spec" / "00_CLEANROOM_SPEC.md").write_text(
                "# Approved Cleanroom Spec\n\n- Required contract: `verifyToken`\n",
                encoding="utf-8",
            )
            self.assertEqual(
                team_cli.main(["reconstruct-inspect", "--project", str(proj), "--target", "contaminated-zone"]),
                0,
            )
            self.assertEqual(
                team_cli.main(
                    ["reconstruct-ledger", "--project", str(proj), "--source", "contaminated-zone", "--apply"]
                ),
                0,
            )
            self.assertTrue((proj / "evidence" / "reconstruction-ledger.json").is_file())

            (proj / "implementation" / "auth.ts").write_text(
                "export function verifyToken(input: string): boolean { return input.length > 0; }\n",
                encoding="utf-8",
            )
            self.assertEqual(
                team_cli.main(["reconstruct-verify", "--project", str(proj), "--candidate", "implementation"]),
                0,
            )
            self.assertEqual(
                team_cli.main(
                    [
                        "reconstruct-compare",
                        "--project",
                        str(proj),
                        "--source",
                        "contaminated-zone",
                        "--candidate",
                        "implementation",
                    ]
                ),
                0,
            )

    def test_universal_router_build_harness_cli_argv_all_hosts(self) -> None:
        for base in ("codex", "claude", "gemini", "opencode", "dsh", "qwen", "aider", "goose", "hermes", "pi", "local"):
            argv = universal_router.build_harness_cli_argv(base, "결제 모듈 보안 감사 및 테스트 작성")
            self.assertTrue(isinstance(argv, list) and len(argv) >= 2)

    def test_mcp_server_jsonrpc_and_expanded_app_scaffolds(self) -> None:
        import io
        from harness import mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "mcp-proj"
            proj.mkdir()
            self.assertEqual(
                team_cli.main(["scaffold-app", "--project", str(proj), "--app", "cleanroom-reconstruct-kit", "--apply"]),
                0,
            )
            self.assertTrue((proj / "contaminated-zone" / "reference_contract.py").is_file())
            self.assertTrue((proj / "implementation" / "reconstructed_service.py").is_file())

            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "dreampia_reconstruct_ledger",
                        "arguments": {"project": str(proj), "source": "contaminated-zone", "apply": True},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "dreampia_reconstruct_verify",
                        "arguments": {"project": str(proj), "candidate": "implementation"},
                    },
                },
            ]
            in_buf = io.BytesIO(
                b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8") for r in requests)
            )
            out_buf = io.BytesIO()
            self.assertEqual(mcp_server.serve_stdio(proj, in_buf, out_buf), 0)
            responses = [json.loads(line.decode("utf-8")) for line in out_buf.getvalue().splitlines() if line.strip()]
            self.assertEqual(len(responses), 4)
            self.assertEqual(responses[0]["result"]["serverInfo"]["name"], "dreampia-skill-mcp")
            self.assertEqual(len(responses[1]["result"]["tools"]), len(mcp_server.MCP_TOOLS))
            verify_payload = json.loads(responses[3]["result"]["content"][0]["text"])
            self.assertEqual(verify_payload["status"], "PASS")
            self.assertEqual(verify_payload["closure_status"], "CLOSED")

    def test_reconstruct_doctor_and_tier2_enrichment(self) -> None:
        from harness import mcp_server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = mcp_server.execute_mcp_tool(root, "dreampia_reconstruct_doctor", {})
            self.assertEqual(doc["status"], "PASS")
            tier1 = doc["tier1_builtin_engine"]  # type: ignore[index]
            tier2 = doc["tier2_external_booster"]  # type: ignore[index]
            self.assertEqual(tier1["status"], "READY")  # type: ignore[index]
            self.assertTrue(tier1["zero_dependency"])  # type: ignore[index]
            self.assertEqual(tier2["total_catalog_count"], len(reconstruct_engine.OPTIONAL_RE_TOOLS))  # type: ignore[index]
            self.assertTrue(isinstance(tier2["recommended_install_commands"], list))  # type: ignore[index]
            self.assertIn("detected_package_managers", tier2)  # type: ignore[operator]

            # Opt-in install plan preview via MCP
            plan_doc = mcp_server.execute_mcp_tool(
                root,
                "dreampia_reconstruct_doctor",
                {"install_tool": "rizin,jadx", "apply": False},
            )
            self.assertEqual(plan_doc["status"], "PASS")
            install_plan = plan_doc["install_plan"]  # type: ignore[index]
            self.assertEqual(install_plan["selected_ids"], ["rizin", "jadx"])  # type: ignore[index]
            self.assertFalse(install_plan["applied"])  # type: ignore[index]
            self.assertEqual(len(install_plan["steps"]), 2)  # type: ignore[index,arg-type]

            # Unknown tool ID returns FAIL status
            bad_doc = mcp_server.execute_mcp_tool(
                root,
                "dreampia_reconstruct_doctor",
                {"install_tool": "nonexistent_tool", "apply": False},
            )
            self.assertEqual(bad_doc["status"], "FAIL")

            pe_path = root / "sample.dll"
            pe_path.write_bytes(_build_minimal_pe64())
            info = reconstruct_engine.inspect_artifact(pe_path)
            self.assertIn("tier2_enrichment", info)
            self.assertIn("deep_symbols", info["tier2_enrichment"])  # type: ignore[operator]

            # [과제 3] reconstruct-spec: auto-generate approved-spec/00_CLEANROOM_SPEC.md and golden-io.json from contaminated-zone
            cz = root / "contaminated-zone"
            cz.mkdir(parents=True, exist_ok=True)
            (cz / "legacy_auth.py").write_text("def verify_token(token: str) -> bool:\n    return bool(token)\n", encoding="utf-8")
            spec_res = mcp_server.execute_mcp_tool(
                root,
                "dreampia_reconstruct_spec",
                {"source": "contaminated-zone", "apply": True},
            )
            self.assertEqual(spec_res["status"], "PASS")
            self.assertTrue((root / "approved-spec" / "00_CLEANROOM_SPEC.md").is_file())
            self.assertTrue((root / "approved-spec" / "golden-io.json").is_file())
            self.assertTrue((root / "evidence" / "reconstruction-ledger.json").is_file())


if __name__ == "__main__":
    unittest.main()


