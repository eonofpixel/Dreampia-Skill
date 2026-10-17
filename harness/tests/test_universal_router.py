"""Unit and integration tests for Dreampia Universal Harness Router (universal_router.py)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import team_cli as team
import universal_router


class UniversalRouterDiscoveryAndReasoningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_discover_harnesses_computes_availability_and_skill_status(self) -> None:
        disc = universal_router.discover_harnesses(
            self.root,
            which_fn=lambda exe: f"/usr/bin/{exe}" if exe in ("codex", "claude", "agy") else None,
        )
        self.assertEqual(disc["default_version"], "1.1.0")
        self.assertTrue(disc["capabilities"]["plugins"])
        by_base = {h["base"]: h for h in disc["harnesses"]}  # type: ignore[index]
        self.assertTrue(by_base["codex"]["available"])
        self.assertTrue(by_base["claude"]["available"])
        self.assertTrue(by_base["gemini"]["available"])
        self.assertFalse(by_base["hermes"]["available"])
        self.assertFalse(by_base["codex"]["skillInstalled"])

        universal_router.materialize_harness(self.root, "codex", apply=True)
        disc_after = universal_router.discover_harnesses(self.root, which_fn=lambda _: None)
        by_base_after = {h["base"]: h for h in disc_after["harnesses"]}  # type: ignore[index]
        self.assertTrue(by_base_after["codex"]["skillInstalled"])

    def test_reasoning_effort_normalization_per_model_family(self) -> None:
        gpt_none = universal_router.normalize_reasoning_effort("openai/gpt-5-codex", "none")
        self.assertEqual(gpt_none["effective_effort"], "low")
        self.assertTrue(gpt_none["substituted"])

        gpt_med = universal_router.normalize_reasoning_effort("gpt-5-codex", "medium")
        self.assertEqual(gpt_med["effective_effort"], "medium")
        self.assertFalse(gpt_med["substituted"])

        gem_min = universal_router.normalize_reasoning_effort("gemini-2.5-pro", "minimal")
        self.assertEqual(gem_min["effective_effort"], "low")
        self.assertTrue(gem_min["substituted"])

        unknown_model = universal_router.normalize_reasoning_effort("custom-unmeasured-model", "high")
        self.assertEqual(unknown_model["effective_effort"], "default")


class UniversalMaterializeAndPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_materialize_preview_vs_apply_and_mcp_formats(self) -> None:
        mcp_servers: list[dict[str, object]] = [
            {
                "name": "rea-mcp",
                "url": "https://mcp.example.invalid/mcp",
                "transport": "http",
                "auth": "tok-123",
                "headers": {"X-Workspace": "dreampia"},
            },
            {
                "name": "sse-probe",
                "url": "https://mcp.example.invalid/sse",
                "transport": "sse",
            },
        ]
        preview = universal_router.materialize_harness(
            self.root, "gemini", mcp_servers=mcp_servers, apply=False
        )
        self.assertFalse(preview["applied"])
        self.assertEqual(list(self.root.iterdir()), [])

        applied = universal_router.materialize_harness(
            self.root, "gemini", mcp_servers=mcp_servers, apply=True
        )
        self.assertTrue(applied["applied"])
        self.assertTrue((self.root / ".gemini/skills/ai-dev-execution/SKILL.md").is_file())
        gemini_cfg = json.loads((self.root / ".gemini/settings.json").read_text(encoding="utf-8"))["mcpServers"]
        self.assertEqual(gemini_cfg["rea_mcp"]["httpUrl"], "https://mcp.example.invalid/mcp")
        self.assertEqual(gemini_cfg["rea_mcp"]["headers"]["Authorization"], "Bearer tok-123")
        self.assertEqual(gemini_cfg["sse_probe"], {"url": "https://mcp.example.invalid/sse"})

        universal_router.materialize_harness(self.root, "codex", mcp_servers=mcp_servers, apply=True)
        toml_text = (self.root / ".harness/codex-mcp.toml").read_text(encoding="utf-8")
        self.assertIn("# Dreampia Managed MCP Configuration", toml_text)
        self.assertIn("[mcp_servers.rea_mcp]", toml_text)
        self.assertIn('"Authorization" = "Bearer tok-123"', toml_text)

    def test_export_router_plugin_strips_credentials_and_records_skipped(self) -> None:
        plugin = universal_router.export_router_plugin(
            mcp_servers=[
                {
                    "name": "vault",
                    "url": "https://mcp.example.invalid/vault",
                    "transport": "http",
                    "auth": "super-secret-token",
                }
            ]
        )
        self.assertEqual(plugin["name"], "dreampia-ai-dev-execution")
        self.assertEqual(len(plugin["skipped"]), 1)  # type: ignore[arg-type]
        files_by_path = {f["path"]: f["content"] for f in plugin["files"] if "content" in f}  # type: ignore[index]
        self.assertIn("plugin.json", files_by_path)
        self.assertIn("mcp.json", files_by_path)
        self.assertIn("skills/ai-dev-execution/SKILL.md", files_by_path)
        self.assertNotIn("super-secret-token", files_by_path["mcp.json"])

    def test_stdio_plugin_launcher_expands_placeholders_and_blocks_escapes(self) -> None:
        universal_router.materialize_harness(self.root, "claude", include_plugin=True, apply=True)
        plugin_root = self.root / ".harness/plugins/dreampia_ai_dev_execution"
        probe_bin = plugin_root / "bin/probe.sh"
        probe_bin.parent.mkdir(parents=True, exist_ok=True)
        probe_bin.write_text(
            "#!/bin/sh\nprintf '%s|%s|%s|%s' \"$PLUGIN_ROOT\" \"$PLUGIN_DATA\" \"$CUSTOM_VAR\" \"$1\"\n",
            encoding="utf-8",
        )
        launchers = universal_router.build_plugin_stdio_launchers(
            self.root,
            "dreampia_ai_dev_execution",
            [
                {
                    "name": "probe",
                    "command": "./bin/probe.sh",
                    "args": ["${PLUGIN_DATA}/state"],
                    "env": {"PLUGIN_ROOT": "/evil/override", "CUSTOM_VAR": "ok-${PLUGIN_ROOT}"},
                },
                {
                    "name": "escape-cmd",
                    "command": "./../../outside.sh",
                },
                {
                    "name": "escape-cwd",
                    "command": "./bin/probe.sh",
                    "cwd": "/etc",
                },
            ],
        )
        self.assertEqual(len(launchers), 1)
        launcher = launchers[0]
        proc = subprocess.run(
            [str(launcher["command"]), *launcher["args"]],  # type: ignore[misc]
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        parts = proc.stdout.split("|")
        expected_root = str(plugin_root.resolve())
        expected_data = str((self.root / ".harness/plugin-data/dreampia_ai_dev_execution").resolve())
        self.assertEqual(parts[0], expected_root)
        self.assertEqual(parts[1], expected_data)
        self.assertEqual(parts[2], f"ok-{expected_root}")
        self.assertEqual(parts[3], f"{expected_data}/state")


class UniversalTaskDispatchAndServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_dispatch_session_continuity_model_fallback_secret_redaction_and_artifacts(self) -> None:
        worker = (
            "from pathlib import Path; "
            "Path('deliverable.txt').write_text('generated output', encoding='utf-8'); "
            "print('done with API_KEY=SUPER_SECRET_VALUE_123456')"
        )
        resp1 = universal_router.dispatch_router_task(
            self.root,
            {
                "input": "학생 제출 결과 파일 생성 기능 구현",
                "model": "legacy-custom-model",
                "metadata": {"harness_id": "dp_node_codex"},
                "tools": [{"type": "function"}],
                "include": ["reasoning"],
            },
            executor_argv=[sys.executable, "-c", worker],
        )
        self.assertEqual(resp1["status"], "completed")
        self.assertEqual(resp1["model"], "gpt-5-codex")
        meta1: dict[str, object] = resp1["metadata"]  # type: ignore[assignment]
        self.assertEqual(meta1["requested_model"], "legacy-custom-model")
        self.assertTrue(meta1["model_fallback"])
        self.assertEqual(meta1["ignored_fields"], ["include", "tools"])
        self.assertEqual(meta1["turn"], 1)

        out_text = resp1["output"][0]["content"][0]["text"]  # type: ignore[index]
        self.assertNotIn("SUPER_SECRET_VALUE_123456", out_text)
        self.assertIn("[REDACTED]", out_text)

        artifacts: list[dict[str, object]] = resp1["artifacts"]  # type: ignore[assignment]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["filename"], "deliverable.txt")

        # Continue session with previous_response_id
        resp2 = universal_router.dispatch_router_task(
            self.root,
            {
                "input": "생성된 결과 파일 코드 리뷰해줘",
                "previous_response_id": resp1["id"],
            },
        )
        meta2: dict[str, object] = resp2["metadata"]  # type: ignore[assignment]
        self.assertEqual(meta2["session_id"], meta1["session_id"])
        self.assertEqual(meta2["turn"], 2)

        # Mismatched harness on session continuation must raise 409 harness_mismatch
        with self.assertRaises(universal_router.RouterError) as ctx:
            universal_router.dispatch_router_task(
                self.root,
                {
                    "input": "다른 하네스로 세션 이어가기 시도",
                    "previous_response_id": resp1["id"],
                    "metadata": {"harness_id": "dp_node_claude"},
                },
            )
        self.assertEqual(ctx.exception.code, "harness_mismatch")
        self.assertEqual(ctx.exception.http_status, 409)

    def test_loopback_router_http_server_and_team_cli_router_actions(self) -> None:
        server = universal_router.create_router_http_server(self.root, "127.0.0.1", 0, api_key="test-router-key")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{port}"
            # Unauthenticated request must return 401
            req_unauth = urllib.request.Request(f"{base_url}/v1/capabilities")
            with self.assertRaises(urllib.error.HTTPError) as err_ctx:
                urllib.request.urlopen(req_unauth, timeout=5)
            self.assertEqual(err_ctx.exception.code, 401)

            # Unsupported X-Dreampia-Router-Version must return 400
            req_bad_ver = urllib.request.Request(
                f"{base_url}/v1/capabilities",
                headers={"Authorization": "Bearer test-router-key", "X-Dreampia-Router-Version": "9.9.9"},
            )
            with self.assertRaises(urllib.error.HTTPError) as err_ver:
                urllib.request.urlopen(req_bad_ver, timeout=5)
            self.assertEqual(err_ver.exception.code, 400)

            # Valid POST /v1/responses
            body = json.dumps(
                {
                    "input": "아키텍처 구조 설명해줘",
                    "metadata": {"harness_id": "dp_node_codex"},
                }
            ).encode("utf-8")
            req_post = urllib.request.Request(
                f"{base_url}/v1/responses",
                data=body,
                headers={
                    "Authorization": "Bearer test-router-key",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_post, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["object"], "response")
                self.assertEqual(data["status"], "completed")
                resp_id = data["id"]

            # GET /v1/responses/{id}
            req_get = urllib.request.Request(
                f"{base_url}/v1/responses/{resp_id}",
                headers={"Authorization": "Bearer test-router-key"},
            )
            with urllib.request.urlopen(req_get, timeout=5) as resp_fetched:
                fetched = json.loads(resp_fetched.read().decode("utf-8"))
                self.assertEqual(fetched["id"], resp_id)
        finally:
            server.shutdown()
            server.server_close()

        # Verify team_cli router-* integration
        disc_cli = team.router_discover_check(self.root)
        self.assertEqual(disc_cli["status"], "PASS")
        disp_cli = team.router_dispatch_check(self.root, "테스트 실행 및 검증", "codex")
        self.assertEqual(disp_cli["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
