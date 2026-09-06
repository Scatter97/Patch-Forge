from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PATCHFORGE_DIR = ".patchforge"
CHECKPOINT_DIR = "checkpoints"
MANIFEST_NAME = "manifest.json"


class PatchForgeError(Exception):
    pass


@dataclass
class PreparedFile:
    relative_path: str
    absolute_path: Path
    original_bytes: bytes
    new_bytes: bytes
    original_sha256: str
    new_sha256: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    output: str = ""


@dataclass
class WorkflowResult:
    prepared: list[PreparedFile]
    checkpoint: Path | None
    preflight: list[CheckResult]
    verify: list[CheckResult]
    applied: bool
    rolled_back: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_repo(path: str | Path) -> Path:
    repo = Path(path).expanduser().resolve()

    if not repo.exists():
        raise PatchForgeError(
            f"Repository path does not exist: {repo}"
        )

    if not repo.is_dir():
        raise PatchForgeError(
            f"Repository path is not a directory: {repo}"
        )

    return repo


def ensure_inside_repo(repo: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(repo.resolve())
    except ValueError as exc:
        raise PatchForgeError(
            f"Path escapes repository: {path}"
        ) from exc


def resolve_repo_path(repo: Path, relative_path: str) -> Path:
    path = (repo / Path(relative_path)).resolve()

    ensure_inside_repo(
        repo,
        path,
    )

    return path


def read_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        raise PatchForgeError(
            f"Could not read JSON file: {path}"
        ) from exc

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PatchForgeError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise PatchForgeError(
            "Top-level patch specification must be an object."
        )

    return value


def parse_json_text(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PatchForgeError(
            f"Invalid JSON: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise PatchForgeError(
            "Top-level patch specification must be an object."
        )

    return value


def require_string(
    obj: dict[str, Any],
    key: str,
    context: str,
) -> str:
    value = obj.get(key)

    if not isinstance(value, str):
        raise PatchForgeError(
            f"{context}: '{key}' must be a string."
        )

    return value


def expected_match_count(
    edit: dict[str, Any],
    context: str,
) -> int:
    value = edit.get(
        "expected_matches",
        1,
    )

    if not isinstance(value, int) or value < 1:
        raise PatchForgeError(
            f"{context}: expected_matches must be an integer >= 1."
        )

    return value


def normalize_newlines(text: str) -> str:
    return (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"

    if "\r" in text:
        return "\r"

    return "\n"


def apply_replace(
    text: str,
    edit: dict[str, Any],
    context: str,
) -> str:
    old = normalize_newlines(
        require_string(
            edit,
            "old",
            context,
        )
    )

    new = normalize_newlines(
        require_string(
            edit,
            "new",
            context,
        )
    )

    expected = expected_match_count(
        edit,
        context,
    )

    count = text.count(old)

    if count != expected:
        raise PatchForgeError(
            f"{context}: replace expected {expected} match(es), found {count}."
        )

    return text.replace(
        old,
        new,
    )


def apply_insert_before(
    text: str,
    edit: dict[str, Any],
    context: str,
) -> str:
    anchor = normalize_newlines(
        require_string(
            edit,
            "anchor",
            context,
        )
    )

    content = normalize_newlines(
        require_string(
            edit,
            "content",
            context,
        )
    )

    expected = expected_match_count(
        edit,
        context,
    )

    count = text.count(anchor)

    if count != expected:
        raise PatchForgeError(
            f"{context}: insert_before expected "
            f"{expected} anchor match(es), found {count}."
        )

    return text.replace(
        anchor,
        content + anchor,
    )


def apply_insert_after(
    text: str,
    edit: dict[str, Any],
    context: str,
) -> str:
    anchor = normalize_newlines(
        require_string(
            edit,
            "anchor",
            context,
        )
    )

    content = normalize_newlines(
        require_string(
            edit,
            "content",
            context,
        )
    )

    expected = expected_match_count(
        edit,
        context,
    )

    count = text.count(anchor)

    if count != expected:
        raise PatchForgeError(
            f"{context}: insert_after expected "
            f"{expected} anchor match(es), found {count}."
        )

    return text.replace(
        anchor,
        anchor + content,
    )


def apply_edit(
    text: str,
    edit: dict[str, Any],
    context: str,
) -> str:
    operation = require_string(
        edit,
        "op",
        context,
    )

    if operation == "replace":
        return apply_replace(
            text,
            edit,
            context,
        )

    if operation == "insert_before":
        return apply_insert_before(
            text,
            edit,
            context,
        )

    if operation == "insert_after":
        return apply_insert_after(
            text,
            edit,
            context,
        )

    raise PatchForgeError(
        f"{context}: unsupported operation '{operation}'."
    )


def validate_spec_version(spec: dict[str, Any]) -> int:
    version = spec.get(
        "version"
    )

    if version not in (1, 2):
        raise PatchForgeError(
            'Patch spec must contain "version": 1 or "version": 2.'
        )

    return version


def prepare_patch(
    repo: Path,
    spec: dict[str, Any],
) -> list[PreparedFile]:
    validate_spec_version(
        spec
    )

    files = spec.get(
        "files"
    )

    if not isinstance(files, list) or not files:
        raise PatchForgeError(
            "Patch spec must contain a non-empty files list."
        )

    prepared: list[PreparedFile] = []
    seen_paths: set[str] = set()

    for file_index, file_spec in enumerate(files):
        context = f"files[{file_index}]"

        if not isinstance(file_spec, dict):
            raise PatchForgeError(
                f"{context} must be an object."
            )

        relative_path = require_string(
            file_spec,
            "path",
            context,
        )

        if relative_path in seen_paths:
            raise PatchForgeError(
                f"Duplicate file in patch: {relative_path}"
            )

        seen_paths.add(
            relative_path
        )

        absolute_path = resolve_repo_path(
            repo,
            relative_path,
        )

        if not absolute_path.exists():
            raise PatchForgeError(
                f"{context}: file does not exist: {relative_path}"
            )

        if not absolute_path.is_file():
            raise PatchForgeError(
                f"{context}: not a regular file: {relative_path}"
            )

        original_bytes = absolute_path.read_bytes()

        original_hash = sha256_bytes(
            original_bytes
        )

        expected_hash = file_spec.get(
            "sha256"
        )

        if expected_hash is not None:
            if not isinstance(
                expected_hash,
                str,
            ):
                raise PatchForgeError(
                    f"{context}: sha256 must be a string."
                )

            if expected_hash.lower() != original_hash.lower():
                raise PatchForgeError(
                    f"{context}: SHA-256 mismatch for "
                    f"{relative_path}\n"
                    f"Expected: {expected_hash}\n"
                    f"Actual:   {original_hash}"
                )

        try:
            original_text = original_bytes.decode(
                "utf-8"
            )
        except UnicodeDecodeError as exc:
            raise PatchForgeError(
                f"{context}: {relative_path} is not valid UTF-8."
            ) from exc

        newline = detect_newline(
            original_text
        )

        normalized_text = normalize_newlines(
            original_text
        )

        edits = file_spec.get(
            "edits"
        )

        if not isinstance(edits, list) or not edits:
            raise PatchForgeError(
                f"{context}: edits must be a non-empty list."
            )

        new_text = normalized_text

        for edit_index, edit in enumerate(edits):
            edit_context = (
                f"{context}.edits[{edit_index}]"
            )

            if not isinstance(edit, dict):
                raise PatchForgeError(
                    f"{edit_context} must be an object."
                )

            new_text = apply_edit(
                new_text,
                edit,
                edit_context,
            )

        output_text = new_text.replace(
            "\n",
            newline,
        )

        new_bytes = output_text.encode(
            "utf-8"
        )

        if new_bytes == original_bytes:
            raise PatchForgeError(
                f"{context}: patch produced no change for {relative_path}."
            )

        prepared.append(
            PreparedFile(
                relative_path=relative_path,
                absolute_path=absolute_path,
                original_bytes=original_bytes,
                new_bytes=new_bytes,
                original_sha256=original_hash,
                new_sha256=sha256_bytes(
                    new_bytes
                ),
            )
        )

    return prepared


def patchforge_root(repo: Path) -> Path:
    return repo / PATCHFORGE_DIR


def checkpoints_root(repo: Path) -> Path:
    return (
        patchforge_root(repo)
        / CHECKPOINT_DIR
    )


def create_checkpoint(
    repo: Path,
    files: list[PreparedFile],
    label: str | None = None,
) -> Path:
    now = datetime.now(
        timezone.utc
    )

    safe_time = now.strftime(
        "%Y%m%dT%H%M%SZ"
    )

    checkpoint_id = (
        safe_time
        + "-"
        + uuid.uuid4().hex[:8]
    )

    root = checkpoints_root(
        repo
    )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )

    checkpoint = (
        root
        / checkpoint_id
    )

    checkpoint.mkdir()

    backup_root = (
        checkpoint
        / "files"
    )

    backup_root.mkdir()

    manifest_files = []

    for item in files:
        destination = (
            backup_root
            / Path(item.relative_path)
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_bytes(
            item.original_bytes
        )

        manifest_files.append(
            {
                "path": item.relative_path,
                "sha256": item.original_sha256,
                "patched_sha256": item.new_sha256,
            }
        )

    manifest = {
        "version": 2,
        "checkpoint_id": checkpoint_id,
        "created_utc": now.isoformat(),
        "label": label,
        "repo": str(repo),
        "files": manifest_files,
    }

    (
        checkpoint
        / MANIFEST_NAME
    ).write_text(
        json.dumps(
            manifest,
            indent=2,
        ),
        encoding="utf-8",
    )

    return checkpoint


def atomic_write(
    destination: Path,
    data: bytes,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix=".patchforge-",
        suffix=".tmp",
        dir=str(destination.parent),
    )

    temp_path = Path(
        temp_name
    )

    try:
        with os.fdopen(
            fd,
            "wb",
        ) as handle:
            handle.write(
                data
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            temp_path,
            destination,
        )

    except Exception:
        try:
            temp_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise


def apply_prepared_files(
    prepared: list[PreparedFile],
) -> None:
    written: list[PreparedFile] = []

    try:
        for item in prepared:
            atomic_write(
                item.absolute_path,
                item.new_bytes,
            )

            written.append(
                item
            )

    except Exception as exc:
        for item in reversed(written):
            try:
                atomic_write(
                    item.absolute_path,
                    item.original_bytes,
                )
            except Exception:
                pass

        raise PatchForgeError(
            "Write failed. Patch Forge attempted "
            "to restore already-written files."
        ) from exc


def print_plan(
    prepared: list[PreparedFile],
) -> None:
    print()
    print(
        "Patch Forge validation passed."
    )
    print()

    for item in prepared:
        print(
            item.relative_path
        )

        print(
            f"  old SHA-256: "
            f"{item.original_sha256}"
        )

        print(
            f"  new SHA-256: "
            f"{item.new_sha256}"
        )

    print()

    print(
        f"{len(prepared)} file(s) ready."
    )


def run_command_capture(
    repo: Path,
    command: str,
    timeout: int | float | None = None,
) -> tuple[int, str]:
    try:
        process = subprocess.run(
            command,
            cwd=repo,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PatchForgeError(
            f"Command timed out after "
            f"{timeout} seconds: {command}"
        ) from exc

    output = process.stdout or ""

    if process.stderr:
        if output and not output.endswith("\n"):
            output += "\n"

        output += process.stderr

    return (
        process.returncode,
        output,
    )


def normalize_check_entries(
    spec: dict[str, Any],
    key: str,
) -> list[Any]:
    value = spec.get(
        key,
        [],
    )

    if value is None:
        return []

    if not isinstance(value, list):
        raise PatchForgeError(
            f"'{key}' must be a list."
        )

    return value


def run_check_entry(
    repo: Path,
    entry: Any,
    context: str,
) -> CheckResult:
    if isinstance(entry, str):
        code, output = run_command_capture(
            repo,
            entry,
        )

        if code != 0:
            raise PatchForgeError(
                f"{context} failed with exit code "
                f"{code}: {entry}\n{output}"
            )

        return CheckResult(
            name=entry,
            passed=True,
            detail="Command passed.",
            output=output,
        )

    if not isinstance(entry, dict):
        raise PatchForgeError(
            f"{context} must be a string or an object."
        )

    check_type = entry.get(
        "type",
        "command",
    )

    if not isinstance(check_type, str):
        raise PatchForgeError(
            f"{context}: type must be a string."
        )

    name = entry.get(
        "name"
    )

    if name is not None and not isinstance(
        name,
        str,
    ):
        raise PatchForgeError(
            f"{context}: name must be a string."
        )

    if check_type == "sha256":
        relative = require_string(
            entry,
            "path",
            context,
        )

        expected = require_string(
            entry,
            "equals",
            context,
        )

        path = resolve_repo_path(
            repo,
            relative,
        )

        if not path.is_file():
            raise PatchForgeError(
                f"{context}: file not found: {relative}"
            )

        actual = sha256_bytes(
            path.read_bytes()
        )

        if actual.lower() != expected.lower():
            raise PatchForgeError(
                f"{context}: SHA-256 mismatch for "
                f"{relative}\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )

        return CheckResult(
            name=name or f"SHA-256 {relative}",
            passed=True,
            detail=f"{relative}: {actual}",
        )

    if check_type == "file_exists":
        relative = require_string(
            entry,
            "path",
            context,
        )

        path = resolve_repo_path(
            repo,
            relative,
        )

        if not path.exists():
            raise PatchForgeError(
                f"{context}: path does not exist: {relative}"
            )

        return CheckResult(
            name=name or f"Exists {relative}",
            passed=True,
            detail=f"Found {relative}.",
        )

    if check_type == "command":
        command = require_string(
            entry,
            "command",
            context,
        )

        expected_exit = entry.get(
            "expect_exit",
            0,
        )

        if not isinstance(expected_exit, int):
            raise PatchForgeError(
                f"{context}: expect_exit must be an integer."
            )

        timeout = entry.get(
            "timeout_seconds"
        )

        if (
            timeout is not None
            and (
                not isinstance(
                    timeout,
                    (int, float),
                )
                or timeout <= 0
            )
        ):
            raise PatchForgeError(
                f"{context}: timeout_seconds must be greater than zero."
            )

        code, output = run_command_capture(
            repo,
            command,
            timeout=timeout,
        )

        if code != expected_exit:
            raise PatchForgeError(
                f"{context}: command returned "
                f"{code}; expected {expected_exit}.\n"
                f"Command: {command}\n"
                f"{output}"
            )

        contains = entry.get(
            "output_contains"
        )

        if contains is not None:
            if not isinstance(
                contains,
                str,
            ):
                raise PatchForgeError(
                    f"{context}: output_contains must be a string."
                )

            if contains not in output:
                raise PatchForgeError(
                    f"{context}: command output "
                    "did not contain expected text "
                    f"{contains!r}.\n"
                    f"Command: {command}\n"
                    f"{output}"
                )

        return CheckResult(
            name=name or command,
            passed=True,
            detail=f"Exit code {code}.",
            output=output,
        )

    raise PatchForgeError(
        f"{context}: unsupported check type '{check_type}'."
    )


def run_checks(
    repo: Path,
    entries: list[Any],
    phase: str,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    for index, entry in enumerate(entries):
        context = f"{phase}[{index}]"

        result = run_check_entry(
            repo,
            entry,
            context,
        )

        results.append(
            result
        )

    return results


def run_preflight(
    repo: Path,
    spec: dict[str, Any],
) -> list[CheckResult]:
    entries = normalize_check_entries(
        spec,
        "preflight",
    )

    return run_checks(
        repo,
        entries,
        "preflight",
    )


def run_verification(
    repo: Path,
    spec: dict[str, Any],
) -> list[CheckResult]:
    entries = normalize_check_entries(
        spec,
        "verify",
    )

    return run_checks(
        repo,
        entries,
        "verify",
    )


def list_checkpoints(repo: Path) -> list[Path]:
    root = checkpoints_root(
        repo
    )

    if not root.exists():
        return []

    return sorted(
        (
            path
            for path in root.iterdir()
            if (
                path.is_dir()
                and (
                    path
                    / MANIFEST_NAME
                ).exists()
            )
        ),
        key=lambda path: path.name,
    )


def load_checkpoint_manifest(
    checkpoint: Path,
) -> dict[str, Any]:
    return read_json(
        checkpoint
        / MANIFEST_NAME
    )


def find_checkpoint(
    repo: Path,
    checkpoint_id: str | None,
) -> Path:
    checkpoints = list_checkpoints(
        repo
    )

    if not checkpoints:
        raise PatchForgeError(
            "No Patch Forge checkpoints exist."
        )

    if checkpoint_id is None:
        return checkpoints[-1]

    matches = [
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.name == checkpoint_id
    ]

    if len(matches) != 1:
        raise PatchForgeError(
            f"Checkpoint not found: {checkpoint_id}"
        )

    return matches[0]


def restore_checkpoint(
    repo: Path,
    checkpoint: Path,
) -> None:
    manifest = load_checkpoint_manifest(
        checkpoint
    )

    files = manifest.get(
        "files"
    )

    if not isinstance(files, list):
        raise PatchForgeError(
            "Checkpoint manifest is invalid."
        )

    restore_items: list[
        tuple[Path, bytes]
    ] = []

    for entry in files:
        if not isinstance(
            entry,
            dict,
        ):
            raise PatchForgeError(
                "Checkpoint manifest contains an invalid file entry."
            )

        relative = require_string(
            entry,
            "path",
            "checkpoint",
        )

        backup = (
            checkpoint
            / "files"
            / relative
        )

        destination = resolve_repo_path(
            repo,
            relative,
        )

        if not backup.exists():
            raise PatchForgeError(
                f"Missing checkpoint file: {relative}"
            )

        restore_items.append(
            (
                destination,
                backup.read_bytes(),
            )
        )

    for destination, data in restore_items:
        atomic_write(
            destination,
            data,
        )


def get_rollback_on_verify_failure(
    spec: dict[str, Any],
) -> bool:
    options = spec.get(
        "options",
        {},
    )

    if options is None:
        return False

    if not isinstance(options, dict):
        raise PatchForgeError(
            "'options' must be an object."
        )

    value = options.get(
        "rollback_on_verify_failure",
        False,
    )

    if not isinstance(value, bool):
        raise PatchForgeError(
            "options.rollback_on_verify_failure must be true or false."
        )

    return value


def run_workflow(
    repo: Path,
    spec: dict[str, Any],
) -> WorkflowResult:
    validate_spec_version(
        spec
    )

    preflight = run_preflight(
        repo,
        spec,
    )

    prepared = prepare_patch(
        repo,
        spec,
    )

    label = spec.get(
        "name"
    )

    if (
        label is not None
        and not isinstance(
            label,
            str,
        )
    ):
        raise PatchForgeError(
            "Patch name must be a string."
        )

    checkpoint = create_checkpoint(
        repo,
        prepared,
        label=label,
    )

    try:
        apply_prepared_files(
            prepared
        )
    except Exception:
        shutil.rmtree(
            checkpoint,
            ignore_errors=True,
        )
        raise

    verify_results: list[CheckResult] = []

    try:
        verify_results = run_verification(
            repo,
            spec,
        )

    except Exception:
        if get_rollback_on_verify_failure(
            spec
        ):
            restore_checkpoint(
                repo,
                checkpoint,
            )

            raise PatchForgeError(
                "Post-apply verification failed. "
                "Patch Forge automatically rolled "
                f"back checkpoint {checkpoint.name}."
            )

        raise

    return WorkflowResult(
        prepared=prepared,
        checkpoint=checkpoint,
        preflight=preflight,
        verify=verify_results,
        applied=True,
        rolled_back=False,
    )


def git_diff_text(repo: Path) -> str:
    environment = os.environ.copy()

    environment["GIT_PAGER"] = "cat"

    try:
        process = subprocess.run(
            [
                "git",
                "--no-pager",
                "diff",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise PatchForgeError(
            "Git was not found in PATH."
        ) from exc

    if process.returncode != 0:
        raise PatchForgeError(
            "git diff failed:\n"
            f"{process.stderr}"
        )

    return process.stdout


def git_diff_check(repo: Path) -> str:
    try:
        process = subprocess.run(
            [
                "git",
                "--no-pager",
                "diff",
                "--check",
            ],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PatchForgeError(
            "Git was not found in PATH."
        ) from exc

    output = process.stdout or ""

    if process.stderr:
        output += process.stderr

    if process.returncode != 0:
        raise PatchForgeError(
            "git diff --check reported a problem:\n"
            f"{output}"
        )

    return output


def cmd_check(
    repo: Path,
    spec_path: Path,
) -> None:
    spec = read_json(
        spec_path
    )

    preflight = run_preflight(
        repo,
        spec,
    )

    for result in preflight:
        print(
            f"[PASS] {result.name}"
        )

    prepared = prepare_patch(
        repo,
        spec,
    )

    print_plan(
        prepared
    )

    print(
        "Dry run only. No files were changed."
    )


def cmd_apply(
    repo: Path,
    spec_path: Path,
) -> None:
    spec = read_json(
        spec_path
    )

    print(
        "Running Patch Forge workflow..."
    )

    print(
        "1/4 Preflight checks"
    )

    preflight = run_preflight(
        repo,
        spec,
    )

    for result in preflight:
        print(
            f"  [PASS] {result.name}"
        )

    print(
        "2/4 Deterministic dry run"
    )

    prepared = prepare_patch(
        repo,
        spec,
    )

    print_plan(
        prepared
    )

    print(
        "3/4 Apply"
    )

    label = spec.get(
        "name"
    )

    if (
        label is not None
        and not isinstance(
            label,
            str,
        )
    ):
        raise PatchForgeError(
            "Patch name must be a string."
        )

    checkpoint = create_checkpoint(
        repo,
        prepared,
        label=label,
    )

    try:
        apply_prepared_files(
            prepared
        )
    except Exception:
        shutil.rmtree(
            checkpoint,
            ignore_errors=True,
        )
        raise

    print(
        "  Patch applied successfully."
    )

    print(
        f"  Checkpoint: {checkpoint.name}"
    )

    print(
        "4/4 Verification"
    )

    try:
        verify_results = run_verification(
            repo,
            spec,
        )

    except Exception:
        if get_rollback_on_verify_failure(
            spec
        ):
            restore_checkpoint(
                repo,
                checkpoint,
            )

            print(
                "  Verification failed."
            )

            print(
                "  Automatic rollback completed."
            )

        raise

    if verify_results:
        for result in verify_results:
            print(
                f"  [PASS] {result.name}"
            )
    else:
        print(
            "  No verification checks configured."
        )

    print()

    print(
        "Patch Forge workflow PASSED."
    )


def cmd_diff(repo: Path) -> None:
    git_diff_check(
        repo
    )

    print(
        git_diff_text(
            repo
        ),
        end="",
    )


def cmd_hash(
    repo: Path,
    relative_path: str,
) -> None:
    path = resolve_repo_path(
        repo,
        relative_path,
    )

    if not path.is_file():
        raise PatchForgeError(
            f"File not found: {relative_path}"
        )

    digest = sha256_bytes(
        path.read_bytes()
    )

    print(
        digest
    )


def cmd_checkpoint_list(repo: Path) -> None:
    checkpoints = list_checkpoints(
        repo
    )

    if not checkpoints:
        print(
            "No Patch Forge checkpoints."
        )
        return

    for checkpoint in checkpoints:
        manifest = load_checkpoint_manifest(
            checkpoint
        )

        label = manifest.get(
            "label"
        )

        if label:
            print(
                f"{checkpoint.name}  {label}"
            )
        else:
            print(
                checkpoint.name
            )


def cmd_rollback(
    repo: Path,
    checkpoint_id: str | None,
) -> None:
    checkpoint = find_checkpoint(
        repo,
        checkpoint_id,
    )

    restore_checkpoint(
        repo,
        checkpoint,
    )

    print(
        "Rolled back checkpoint: "
        f"{checkpoint.name}"
    )


def cmd_verify(
    repo: Path,
    spec_path: Path,
) -> None:
    spec = read_json(
        spec_path
    )

    results = run_verification(
        repo,
        spec,
    )

    if not results:
        raise PatchForgeError(
            "Patch spec contains no verify commands."
        )

    for result in results:
        print(
            f"[PASS] {result.name}"
        )

        if result.output:
            print(
                result.output,
                end=(
                    ""
                    if result.output.endswith("\n")
                    else "\n"
                ),
            )

    print()

    print(
        "All verification commands passed."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchforge",
        description=(
            "Deterministic, validated source patching tool."
        ),
    )

    parser.add_argument(
        "--repo",
        default=".",
        help=(
            "Repository directory. "
            "Defaults to the current directory."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    check = subparsers.add_parser(
        "check",
        help=(
            "Run preflight checks and validate "
            "the patch without writing files."
        ),
    )

    check.add_argument(
        "patch",
    )

    apply_command = subparsers.add_parser(
        "apply",
        help=(
            "Run the complete safe patch workflow: "
            "preflight, dry run, checkpoint, apply, "
            "and verification."
        ),
    )

    apply_command.add_argument(
        "patch",
    )

    subparsers.add_parser(
        "diff",
        help=(
            "Run git diff --check and print the complete git diff."
        ),
    )

    hash_command = subparsers.add_parser(
        "hash",
        help=(
            "Print a file's SHA-256 hash."
        ),
    )

    hash_command.add_argument(
        "file",
    )

    rollback = subparsers.add_parser(
        "rollback",
        help=(
            "Restore a Patch Forge checkpoint."
        ),
    )

    rollback.add_argument(
        "checkpoint",
        nargs="?",
        default=None,
        help=(
            "Checkpoint ID. Defaults to the latest checkpoint."
        ),
    )

    subparsers.add_parser(
        "checkpoints",
        help=(
            "List available checkpoints."
        ),
    )

    verify = subparsers.add_parser(
        "verify",
        help=(
            "Run post-apply verification from a patch spec."
        ),
    )

    verify.add_argument(
        "patch",
    )

    return parser


def main() -> int:
    parser = build_parser()

    args = parser.parse_args()

    try:
        repo = normalize_repo(
            args.repo
        )

        if args.command == "check":
            cmd_check(
                repo,
                Path(
                    args.patch
                ).resolve(),
            )

        elif args.command == "apply":
            cmd_apply(
                repo,
                Path(
                    args.patch
                ).resolve(),
            )

        elif args.command == "diff":
            cmd_diff(
                repo
            )

        elif args.command == "hash":
            cmd_hash(
                repo,
                args.file,
            )

        elif args.command == "rollback":
            cmd_rollback(
                repo,
                args.checkpoint,
            )

        elif args.command == "checkpoints":
            cmd_checkpoint_list(
                repo
            )

        elif args.command == "verify":
            cmd_verify(
                repo,
                Path(
                    args.patch
                ).resolve(),
            )

        else:
            raise PatchForgeError(
                f"Unknown command: {args.command}"
            )

        return 0

    except PatchForgeError as exc:
        print(
            f"Patch Forge error: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )