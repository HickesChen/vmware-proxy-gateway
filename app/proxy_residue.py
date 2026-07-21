"""Rule-driven discovery and cleanup of persistent proxy settings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


MAX_SCAN_BYTES = 2 * 1024 * 1024
DEFAULT_RULES = Path(__file__).resolve().parent / "proxy_residue_rules.json"
USER_RULES_NAME = "proxy-residue-rules.json"


class ResidueError(RuntimeError):
    pass


def _read_rules(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ResidueError(f"Invalid proxy residue rule file: {path}")
    return data


def load_rules(home: Path, rules_path: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Load defaults and overlay rules by id so matching can evolve independently."""
    source = rules_path or DEFAULT_RULES
    base = _read_rules(source)
    ordered: dict[str, dict[str, Any]] = {}
    for rule in base["rules"]:
        if isinstance(rule, dict) and rule.get("id"):
            ordered[str(rule["id"])] = rule

    loaded_from = [str(source)]
    override = home / ".config" / "vm-proxy-gateway" / USER_RULES_NAME
    if rules_path is None and override.exists():
        custom = _read_rules(override)
        if custom.get("replace_defaults") is True:
            ordered.clear()
        for rule in custom["rules"]:
            if not isinstance(rule, dict) or not rule.get("id"):
                continue
            rule_id = str(rule["id"])
            if any(not str(item).startswith("{home}/") for item in rule.get("paths") or []):
                raise ResidueError(f"User rule {rule_id} may only scan paths below {{home}}")
            if rule.get("enabled") is False:
                ordered.pop(rule_id, None)
            else:
                ordered[rule_id] = rule
        loaded_from.append(str(override))

    rules = list(ordered.values())
    for rule in rules:
        try:
            re.compile(str(rule["pattern"]))
        except (KeyError, re.error) as exc:
            raise ResidueError(f"Invalid pattern in rule {rule.get('id', '?')}: {exc}") from exc
        if rule.get("cleanup", "remove_line") not in {"remove_line", "regex_substitute"}:
            raise ResidueError(f"Unsupported cleanup action in rule {rule.get('id', '?')}")
    return rules, loaded_from


def _expand_paths(rule: dict[str, Any], home: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for template in rule.get("paths") or []:
        template = str(template)
        rendered = template.replace("{home}", str(home))
        candidate = Path(rendered)
        if any(char in rendered for char in "*?["):
            anchor = Path("/") if candidate.is_absolute() else home
            pattern = rendered[1:] if candidate.is_absolute() else rendered
            paths = anchor.glob(pattern)
        else:
            paths = [candidate]
        for path in paths:
            if path.is_symlink():
                continue
            try:
                normalized = path.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if template.startswith("{home}/"):
                try:
                    normalized.relative_to(home.resolve())
                except ValueError:
                    continue
            if normalized in seen or not normalized.is_file():
                continue
            seen.add(normalized)
            found.append(normalized)
    return found


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mask_proxy_credentials(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return raw
        if parsed.username is None:
            return raw
        hostname = parsed.hostname or ""
        if parsed.port:
            hostname += f":{parsed.port}"
        return urlunsplit((parsed.scheme, f"***:***@{hostname}", parsed.path, parsed.query, parsed.fragment))

    return re.sub(r"(?i)\b(?:https?|socks5h?|ftp)://[^\s\"']+", replace, value)


def scan_proxy_residue(home: Path, rules_path: Path | None = None) -> dict[str, Any]:
    home = home.resolve()
    rules, loaded_from = load_rules(home, rules_path)
    findings: list[dict[str, Any]] = []
    scanned: set[Path] = set()
    skipped: list[dict[str, str]] = []

    for rule in rules:
        pattern = re.compile(str(rule["pattern"]))
        for path in _expand_paths(rule, home):
            scanned.add(path)
            try:
                info = path.stat()
                if info.st_size > int(rule.get("max_bytes") or MAX_SCAN_BYTES):
                    skipped.append({"path": str(path), "reason": "file_too_large"})
                    continue
                raw = path.read_bytes()
                if b"\x00" in raw:
                    skipped.append({"path": str(path), "reason": "binary_file"})
                    continue
                content = raw.decode("utf-8", errors="replace")
            except OSError as exc:
                skipped.append({"path": str(path), "reason": str(exc)})
                continue
            digest = _sha256(raw)
            for line_number, line in enumerate(content.splitlines(), 1):
                match = pattern.search(line)
                if not match:
                    continue
                fingerprint = hashlib.sha256(
                    f"{rule['id']}\0{path}\0{line_number}\0{line}".encode("utf-8", errors="replace")
                ).hexdigest()[:24]
                findings.append({
                    "id": fingerprint,
                    "rule_id": str(rule["id"]),
                    "application": str(rule.get("application") or rule["id"]),
                    "path": str(path),
                    "line": line_number,
                    "preview": _mask_proxy_credentials(line.strip())[:500],
                    "file_sha256": digest,
                    "cleanup": str(rule.get("cleanup") or "remove_line"),
                })

    return {
        "home": str(home),
        "rules_loaded_from": loaded_from,
        "rule_count": len(rules),
        "scanned_file_count": len(scanned),
        "finding_count": len(findings),
        "findings": findings,
        "skipped": skipped,
    }


def _backup_target(path: Path, home: Path, backup_root: Path) -> Path:
    try:
        relative = path.relative_to(home)
        prefix = "home"
    except ValueError:
        relative = Path(*path.parts[1:]) if path.is_absolute() else path
        prefix = "system"
    target = backup_root / prefix / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def _write_preserving_metadata(path: Path, content: str, original: os.stat_result) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".vm-proxy-gateway.tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(temporary, stat.S_IMODE(original.st_mode))
        if hasattr(os, "chown"):
            os.chown(temporary, original.st_uid, original.st_gid)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def clean_proxy_residue(home: Path, selected: list[dict[str, Any]], rules_path: Path | None = None) -> dict[str, Any]:
    """Remove only selected, unchanged lines and create a restorable backup."""
    home = home.resolve()
    rules, _ = load_rules(home, rules_path)
    known_rules = {str(rule["id"]): rule for rule in rules}
    grouped: dict[Path, list[dict[str, Any]]] = {}
    for item in selected:
        if not isinstance(item, dict) or str(item.get("rule_id")) not in known_rules:
            raise ResidueError("The cleanup selection contains an unknown rule")
        path = Path(str(item.get("path") or "")).resolve(strict=True)
        allowed = set(_expand_paths(known_rules[str(item["rule_id"])], home))
        if path not in allowed:
            raise ResidueError(f"Path is no longer allowed by rule {item['rule_id']}: {path}")
        grouped.setdefault(path, []).append(item)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_base = home / ".config" / "vm-proxy-gateway" / "proxy-cleanup-backups"
    try:
        backup_base.resolve(strict=False).relative_to(home)
    except ValueError as exc:
        raise ResidueError("The backup directory must remain below the user home") from exc
    backup_root = backup_base / stamp
    backup_initialized = False
    cleaned: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    for path, items in grouped.items():
        try:
            original = path.stat()
            raw = path.read_bytes()
            expected_hashes = {str(item.get("file_sha256") or "") for item in items}
            if expected_hashes != {_sha256(raw)}:
                raise ResidueError("file changed after scanning; scan again")
            text = raw.decode("utf-8")
            lines = text.splitlines(keepends=True)
            selected_lines = {int(item["line"]) for item in items}
            if not selected_lines or min(selected_lines) < 1 or max(selected_lines) > len(lines):
                raise ResidueError("selected line no longer exists")
            for item in items:
                line_number = int(item["line"])
                line = lines[line_number - 1].rstrip("\r\n")
                rule = known_rules[str(item["rule_id"])]
                if not re.search(str(rule["pattern"]), line):
                    raise ResidueError("selected line does not match the cleanup rule")
                expected_id = hashlib.sha256(
                    f"{item['rule_id']}\0{path}\0{line_number}\0{line}".encode("utf-8", errors="replace")
                ).hexdigest()[:24]
                if item.get("id") != expected_id:
                    raise ResidueError("selected finding fingerprint is invalid")

            if not backup_initialized:
                backup_root.mkdir(parents=True, exist_ok=False)
                backup_initialized = True
            _backup_target(path, home, backup_root)
            items_by_line: dict[int, list[dict[str, Any]]] = {}
            for item in items:
                items_by_line.setdefault(int(item["line"]), []).append(item)
            output_lines: list[str] = []
            for index, original_line in enumerate(lines, 1):
                line_items = items_by_line.get(index)
                if not line_items:
                    output_lines.append(original_line)
                    continue
                if any(known_rules[str(item["rule_id"])].get("cleanup", "remove_line") == "remove_line" for item in line_items):
                    continue
                line_ending = "\r\n" if original_line.endswith("\r\n") else ("\n" if original_line.endswith("\n") else "")
                edited = original_line.removesuffix(line_ending) if line_ending else original_line
                for item in line_items:
                    rule = known_rules[str(item["rule_id"])]
                    edited = re.sub(str(rule["pattern"]), str(rule.get("replacement") or ""), edited)
                output_lines.append(edited.rstrip() + line_ending)
            output = "".join(output_lines)
            if path.suffix.lower() in {".json", ".jsonc"}:
                output = re.sub(r",(?=\s*[}\]])", "", output)
            _write_preserving_metadata(path, output, original)
            for item in items:
                cleaned.append({"id": item.get("id"), "path": str(path), "line": item.get("line")})
        except (OSError, UnicodeError, ValueError, ResidueError) as exc:
            failed.append({"path": str(path), "reason": str(exc)})

    manifest: Path | None = None
    if backup_initialized:
        if cleaned:
            manifest = backup_root / "manifest.json"
            manifest.write_text(json.dumps({"cleaned": cleaned}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            owner = home.stat()
            for backup_item in [backup_root, *backup_root.rglob("*")]:
                relative_parts = backup_item.relative_to(backup_root).parts
                if backup_item.is_dir() or (relative_parts and relative_parts[0] == "home") or backup_item == manifest:
                    os.chown(backup_item, owner.st_uid, owner.st_gid)
        except OSError:
            pass
    return {
        "cleaned_count": len(cleaned),
        "failed_count": len(failed),
        "cleaned": cleaned,
        "failed": failed,
        "backup_path": str(backup_root) if backup_initialized else None,
    }
