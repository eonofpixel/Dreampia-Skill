"""Dependency-free focused skill frontmatter and local Markdown link check."""
from __future__ import annotations

from pathlib import Path
import re
import sys


def validate_skill_assets(skill_root: Path) -> dict[str, object]:
    """스킬 디렉터리의 SKILL.md 프론트매터 규격과 로컬 마크다운 링크 무결성을 검증한다."""
    root = skill_root.resolve()
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    parts = skill_text.split("---", 2)
    assert len(parts) == 3 and not parts[0].strip(), "frontmatter delimiters"
    fields: dict[str, str] = {}
    for line in parts[1].splitlines():
        if line.strip():
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    assert set(fields) == {"name", "description"}, "name and description only"
    assert fields["name"] == root.name and re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert fields["description"], "description required"

    broken: list[tuple[str, str]] = []
    checked = 0
    for md_path in root.rglob("*.md"):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", md_path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#") or "{{" in target:
                continue
            rel_path = target.split("#", 1)[0]
            if not rel_path:
                continue
            checked += 1
            if not (md_path.parent / rel_path).exists():
                broken.append((str(md_path.relative_to(root)), target))

    return {
        "status": "PASS" if not broken else "FAIL",
        "checked_links": checked,
        "broken_links": broken,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점: 인자로 전달된 스킬 디렉터리를 검증한다."""
    args = argv if argv is not None else sys.argv[1:]
    target = Path(args[0]).resolve() if args else Path("ai-dev-execution").resolve()
    result = validate_skill_assets(target)
    if result["status"] != "PASS":
        print(result["broken_links"])
        return 1
    print(f"PASS: focused frontmatter, {result['checked_links']} local file links (anchor semantics not checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

