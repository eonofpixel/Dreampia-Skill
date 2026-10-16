"""Reproduce package verification; logs are for this public deterministic suite only."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys


def run_package_verification(root_dir: Path | None = None, timeout_sec: int = 240) -> dict[str, object]:
    """패키지 전체 검증 스위트를 실행하고 evidence/verification.json을 갱신한다."""
    root = (root_dir or Path(__file__).resolve().parents[1]).resolve()
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    commands: list[list[str]] = [
        [sys.executable, "-m", "unittest", "discover", "-s", "harness/tests", "-v"],
        [sys.executable, "harness/validate_assets.py", "ai-dev-execution"],
        [sys.executable, "harness/cli.py", "validate", "harness/examples/slots"],
        [sys.executable, "harness/cli.py", "run", "harness/examples/slots"],
        [sys.executable, "harness/cli.py", "trace", "harness/examples/slots"],
        [sys.executable, "harness/cli.py", "status", "harness/examples/slots"],
        [sys.executable, "-m", "unittest", "discover", "-s", ".", "-v"],
    ]
    results: list[dict[str, object]] = []
    for i, cmd in enumerate(commands):
        cwd = root / "harness/examples/slots" if i == len(commands) - 1 else root
        at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        log = evidence / f"verify-{i + 1:02d}.txt"
        log.write_text(
            "UTC: "
            + at
            + "\nCWD: "
            + str(cwd)
            + "\nCOMMAND: "
            + json.dumps(cmd)
            + "\nEXIT: "
            + str(proc.returncode)
            + "\n"
            + proc.stdout
            + proc.stderr,
            encoding="utf-8",
        )
        results.append({"command": cmd, "cwd": str(cwd), "at": at, "exit": proc.returncode, "log": log.name})

    files: dict[str, str] = {}
    for p in sorted((root / "harness").rglob("*")):
        if p.is_file() and not any(x in (".harness", "__pycache__") for x in p.parts):
            files[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()

    (evidence / "verification.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "commands": results,
                "source_files": files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    all_pass = all(x["exit"] == 0 for x in results)
    return {"commands": len(results), "all_pass": all_pass}


def main() -> int:
    """CLI 진입점: 전체 패키지 검증을 실행하고 종료 코드를 반환한다."""
    summary = run_package_verification()
    print(json.dumps(summary, indent=2))
    return 0 if bool(summary["all_pass"]) else 1


if __name__ == "__main__":
    sys.exit(main())

