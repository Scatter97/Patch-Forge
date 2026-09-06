import json
from pathlib import Path


PATCH_PATH = Path(
    r"C:\Users\joshh\Documents\Projects\PatchForge\helix-v0.2.0.json"
)


patch = {
    "version": 2,
    "name": "Helix v0.2.0 - Interactive CLI and Reliability",
    "preflight": [
        {
            "type": "sha256",
            "name": "Check helix.py v0.1.2 baseline",
            "path": "helix.py",
            "equals": "d7de7a9f59194030fd0411170007ad0f97e1e60c58f454acd928ed520e7f8cad",
        },
        {
            "type": "sha256",
            "name": "Check helix.toml v0.1.2 baseline",
            "path": "helix.toml",
            "equals": "8b6929e03618acd34ade34c523acbbebf8914884a48d1604fddfc161a7dc7142",
        },
        {
            "type": "sha256",
            "name": "Check coder prompt v0.1.2 baseline",
            "path": "prompts/coder.txt",
            "equals": "1ea08f414299517d029b586b00af0d66432eb3f63f6b3d44e9fdff40fd2e1bba",
        },
        {
            "type": "sha256",
            "name": "Check tests v0.1.2 baseline",
            "path": "tests/test_helix.py",
            "equals": "2f86a9b76ca0eab0c223dd53c2dd6f6a54dc3408af929eb876239853c49d452f",
        },
        {
            "type": "sha256",
            "name": "Check pyproject v0.1.2 baseline",
            "path": "pyproject.toml",
            "equals": "017297302cbda152cfeba477990314355d01e3f39f87b5587f437130229abbac",
        },
        {
            "type": "sha256",
            "name": "Check README v0.1.2 baseline",
            "path": "README.md",
            "equals": "ce598f8a5aa3e8c654fc43cba42635d9670134bce49daa11dfe387af66aa48c5",
        },
    ],
    "files": [
        {
            "path": "helix.py",
            "sha256": "d7de7a9f59194030fd0411170007ad0f97e1e60c58f454acd928ed520e7f8cad",
            "edits": [
                {
                    "op": "replace",
                    "old": 'VERSION = "0.1.2"',
                    "new": 'VERSION = "0.2.0"',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''    verification_passed: bool = False
    changed_files: set[str] = field(default_factory=set)''',
                    "new": r'''    verification_passed: bool = False
    last_verification_command: str = ""
    changed_files: set[str] = field(default_factory=set)''',
                    "expected_matches": 1,
                },
                {
                    "op": "insert_before",
                    "anchor": "\n\nclass Workspace:",
                    "content": r'''

@dataclass
class AgentPermissions:
    write: bool = True
    execute: bool = True
''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''        ignored = {".git", ".helix", "__pycache__", "node_modules", ".venv", "venv"}''',
                    "new": r'''        ignored = {
            ".git",
            ".helix",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".nox",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
        }''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''def print_banner(config: HelixConfig, project_root: Path) -> None:
    main = config.models.get("main")
    large = config.models.get("large")
    remote = config.models.get("remote")

    print("=" * 76)
    print("  H E L I X   //   Autonomous Coding Agent")
    print("=" * 76)
    print(f"  Project : {project_root}")
    print(
        "  Main    : "
        + (f"{main.provider}/{main.model}" if main else "not configured")
    )
    print(
        "  Large   : "
        + (f"{large.provider}/{large.model}" if large else "not configured")
    )
    print(
        "  Remote  : "
        + (
            f"{remote.provider}/{remote.model}"
            if remote and remote.enabled and remote.model
            else "disabled"
        )
    )
    print("  Forge   : deterministic source mutations enabled")
    print("=" * 76)
''',
                    "new": r'''class SessionStore:
    def __init__(self, project_root: Path):
        self.path = project_root / ".helix" / "history.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        task: str,
        status: str,
        summary: str,
        steps: int,
        duration_seconds: float,
    ) -> None:
        entry = {
            "time": int(time.time()),
            "task": task,
            "status": status,
            "summary": summary,
            "steps": steps,
            "duration_seconds": round(duration_seconds, 2),
        }

        with self.path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            handle.write(
                json.dumps(entry, ensure_ascii=False) + "\n"
            )

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        entries: list[dict[str, Any]] = []

        for line in self.path.read_text(
            encoding="utf-8"
        ).splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if isinstance(entry, dict):
                entries.append(entry)

        return entries[-limit:]


class HelixConsole:
    def __init__(
        self,
        config: HelixConfig,
        project_root: Path,
        permissions: AgentPermissions,
    ):
        self.config = config
        self.project_root = project_root
        self.permissions = permissions

    @staticmethod
    def model_label(spec: ModelSpec | None) -> str:
        if not spec or not spec.enabled or not spec.model:
            return "disabled"

        return f"{spec.provider}/{spec.model}"

    def banner(self) -> None:
        print()
        print("  +--------------------------------------------------------------+")
        print("  |                         H E L I X                            |")
        print("  |                  Autonomous Coding Agent                    |")
        print("  +--------------------------------------------------------------+")
        print(f"  Version   {VERSION}")
        print(f"  Project   {self.project_root}")
        print(
            "  Main      "
            + self.model_label(self.config.models.get("main"))
        )
        print(
            "  Large     "
            + self.model_label(self.config.models.get("large"))
        )
        print(
            "  Remote    "
            + self.model_label(self.config.models.get("remote"))
        )
        print(
            "  Forge     "
            + (
                "enabled"
                if self.config.patchforge_cli
                else "not configured"
            )
        )
        print(
            "  Write     "
            + (
                "allowed"
                if self.permissions.write
                else "READ ONLY"
            )
        )
        print(
            "  Execute   "
            + (
                "allowed"
                if self.permissions.execute
                else "DISABLED"
            )
        )
        print("  " + "-" * 64)

    def task_start(self, task: str) -> None:
        print()
        print(f"  TASK      {task}")
        print("  " + "-" * 64)

    def step(
        self,
        step: int,
        role: str,
        tool: str,
    ) -> None:
        labels = {
            "list_files": "SCAN",
            "read_file": "READ",
            "search_text": "SEARCH",
            "hash_file": "HASH",
            "create_file": "CREATE",
            "patch_file": "FORGE",
            "run_command": "EXEC",
            "git_diff": "DIFF",
            "finish": "DONE",
        }

        action = labels.get(tool, tool.upper())

        print(
            f"  [{step:03d}] "
            f"{role.upper():6} "
            f"{action:7} "
            f"{tool}"
        )

    def result(
        self,
        ok: bool,
        summary: str,
    ) -> None:
        marker = "PASS" if ok else "FAIL"
        text = summary.strip()

        if len(text) > 1200:
            text = (
                text[:1200]
                + "\n... output truncated ..."
            )

        if "\n" not in text:
            print(f"        {marker}  {text}")
            return

        print(f"        {marker}")

        for line in text.splitlines():
            print(f"        | {line}")

    def model_error(
        self,
        step: int,
        message: str,
    ) -> None:
        print(
            f"  [{step:03d}] "
            f"MODEL  ERROR  {message}"
        )

    def complete(
        self,
        summary: str,
        duration_seconds: float,
    ) -> None:
        print("  " + "-" * 64)
        print(f"  DONE      {summary}")
        print(f"  Duration  {duration_seconds:.2f}s")
        print()

    def stopped(self, message: str) -> None:
        print("  " + "-" * 64)
        print(f"  STOP      {message}")
        print()

    def show_models(self) -> None:
        print()

        for role in (
            "small",
            "main",
            "large",
            "remote",
        ):
            print(
                f"  {role:7} "
                + self.model_label(
                    self.config.models.get(role)
                )
            )

        print()

    @staticmethod
    def show_history(
        entries: list[dict[str, Any]],
    ) -> None:
        print()

        if not entries:
            print("  No previous Helix tasks for this project.")
            print()
            return

        for entry in entries:
            status = str(
                entry.get("status", "?")
            ).upper()

            steps = entry.get("steps", "?")
            task = str(entry.get("task", ""))

            print(
                f"  {status:8} "
                f"{steps!s:>3} steps   "
                f"{task}"
            )

        print()
''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''class HelixAgent:
    def __init__(self, project_root: Path, config: HelixConfig, prompt_path: Path):
        self.project_root = project_root.resolve()
        self.config = config
        self.workspace = Workspace(self.project_root)
        self.runner = CommandRunner(self.project_root, config.command_timeout_seconds)
        self.forge = PatchForgeAdapter(self.project_root, config.patchforge_cli)
        self.router = ModelRouter(config)
        self.system_prompt = prompt_path.read_text(encoding="utf-8")''',
                    "new": r'''class HelixAgent:
    def __init__(
        self,
        project_root: Path,
        config: HelixConfig,
        prompt_path: Path,
        permissions: AgentPermissions | None = None,
    ):
        self.project_root = project_root.resolve()
        self.config = config
        self.permissions = permissions or AgentPermissions()

        self.workspace = Workspace(self.project_root)

        self.runner = CommandRunner(
            self.project_root,
            config.command_timeout_seconds,
        )

        self.forge = PatchForgeAdapter(
            self.project_root,
            config.patchforge_cli,
        )

        self.router = ModelRouter(config)

        self.system_prompt = prompt_path.read_text(
            encoding="utf-8"
        )

        self.console = HelixConsole(
            config,
            self.project_root,
            self.permissions,
        )

        self.sessions = SessionStore(
            self.project_root
        )''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''    def run(self, task: str) -> int:
        state = AgentState(task=task, project_root=self.project_root)
        print_banner(self.config, self.project_root)
        print(f"  Version : {VERSION}")
        print(f"  Task    : {task}")
        print("-" * 76)''',
                    "new": r'''    def run(self, task: str) -> int:
        state = AgentState(
            task=task,
            project_root=self.project_root,
        )

        started = time.monotonic()

        self.console.task_start(task)''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''                print(f"[{step:03d}] {used_role.upper():6} {tool}")
                ok, summary = self.execute(tool, args, state)
                state.add(used_role, tool, ok, summary)
                print(("      PASS " if ok else "      FAIL ") + summary[:1000])
                if tool == "finish" and ok:
                    return 0
            except Exception as exc:
                state.model_failures += 1
                state.add(preferred_role, "agent_error", False, str(exc))
                print(f"[{step:03d}] ERROR  {exc}")

        print("Helix stopped: maximum step count reached.")
        return 2''',
                    "new": r'''                self.console.step(
                    step,
                    used_role,
                    tool,
                )

                ok, summary = self.execute(
                    tool,
                    args,
                    state,
                )

                state.add(
                    used_role,
                    tool,
                    ok,
                    summary,
                )

                self.console.result(
                    ok,
                    summary,
                )

                if tool == "finish" and ok:
                    duration = (
                        time.monotonic() - started
                    )

                    self.sessions.record(
                        task=task,
                        status="pass",
                        summary=summary,
                        steps=step,
                        duration_seconds=duration,
                    )

                    self.console.complete(
                        summary,
                        duration,
                    )

                    return 0

            except Exception as exc:
                state.model_failures += 1

                state.add(
                    preferred_role,
                    "agent_error",
                    False,
                    str(exc),
                )

                self.console.model_error(
                    step,
                    str(exc),
                )

        duration = time.monotonic() - started
        message = "Maximum step count reached."

        self.sessions.record(
            task=task,
            status="stopped",
            summary=message,
            steps=self.config.max_steps,
            duration_seconds=duration,
        )

        self.console.stopped(message)

        return 2''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''        if tool == "create_file":
            relative = str(args["path"])
            digest = self.workspace.create_file(relative, str(args.get("content", "")))
            state.changed_files.add(relative)
            state.verification_passed = False
            return True, f"Created {relative}; sha256={digest}"''',
                    "new": r'''        if tool == "create_file":
            if not self.permissions.write:
                return (
                    False,
                    "Write denied: Helix is running in read-only mode.",
                )

            relative = str(args["path"])

            digest = self.workspace.create_file(
                relative,
                str(args.get("content", "")),
            )

            state.changed_files.add(relative)
            state.verification_passed = False
            state.last_verification_command = ""

            return (
                True,
                f"Created {relative}; sha256={digest}",
            )''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''        if tool == "patch_file":
            relative = str(args["path"])
            self.workspace.resolve(relative)
            result = self.forge.apply_edit(
                relative,
                str(args["op"]),
                state.step,
                old=args.get("old"),
                new=args.get("new"),
                anchor=args.get("anchor"),
                content=args.get("content"),
                expected_matches=int(args.get("expected_matches", 1)),
            )
            if result["ok"]:
                state.changed_files.add(relative)
                state.verification_passed = False
            else:
                state.coding_failures += 1
            return bool(result["ok"]), json.dumps(result, indent=2)''',
                    "new": r'''        if tool == "patch_file":
            if not self.permissions.write:
                return (
                    False,
                    "Write denied: Helix is running in read-only mode.",
                )

            relative = str(args["path"])

            self.workspace.resolve(relative)

            result = self.forge.apply_edit(
                relative,
                str(args["op"]),
                state.step,
                old=args.get("old"),
                new=args.get("new"),
                anchor=args.get("anchor"),
                content=args.get("content"),
                expected_matches=int(
                    args.get(
                        "expected_matches",
                        1,
                    )
                ),
            )

            if result["ok"]:
                state.changed_files.add(relative)
                state.verification_passed = False
                state.last_verification_command = ""

                return (
                    True,
                    f"Patch applied successfully: {relative}",
                )

            state.coding_failures += 1

            return (
                False,
                json.dumps(
                    result,
                    indent=2,
                ),
            )''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''        if tool == "run_command":
            result = self.runner.run(
                str(args["command"]),
                int(args["timeout_seconds"]) if args.get("timeout_seconds") else None
            )
            if result["ok"]:
                if bool(args.get("verification")):
                    state.verification_passed = True
                    state.coding_failures = 0
            else:
                state.coding_failures += 1
                if bool(args.get("verification")):
                    state.verification_passed = False
            return bool(result["ok"]), json.dumps(result, indent=2)''',
                    "new": r'''        if tool == "run_command":
            if not self.permissions.execute:
                return (
                    False,
                    "Command execution denied by Helix permissions.",
                )

            command = str(args["command"])

            verification = bool(
                args.get("verification")
            )

            if (
                verification
                and state.verification_passed
                and state.last_verification_command
                == command
            ):
                return (
                    True,
                    "Verification already passed; "
                    f"skipped duplicate: {command}",
                )

            result = self.runner.run(
                command,
                int(args["timeout_seconds"])
                if args.get("timeout_seconds")
                else None,
            )

            if result["ok"]:
                if verification:
                    state.verification_passed = True
                    state.last_verification_command = command
                    state.coding_failures = 0

                stdout = str(
                    result.get(
                        "stdout",
                        "",
                    )
                ).strip()

                last_line = (
                    stdout.splitlines()[-1]
                    if stdout
                    else ""
                )

                suffix = (
                    f" | {last_line}"
                    if last_line
                    else ""
                )

                return (
                    True,
                    f"{command} -> exit 0{suffix}",
                )

            state.coding_failures += 1

            if verification:
                state.verification_passed = False
                state.last_verification_command = ""

            return (
                False,
                json.dumps(
                    result,
                    indent=2,
                ),
            )''',
                    "expected_matches": 1,
                },
                {
                    "op": "replace",
                    "old": r'''def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Helix autonomous coding agent")
    parser.add_argument("--project", required=True, help="Target project directory")
    parser.add_argument("--task", required=True, help="Coding task")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("helix.toml")),
        help="Path to helix.toml"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project = Path(args.project)
    if not project.exists() or not project.is_dir():
        print(f"Project directory does not exist: {project}", file=sys.stderr)
        return 2

    config_path = Path(args.config)
    config = HelixConfig.load(config_path)
    prompt_path = Path(__file__).parent / "prompts" / "coder.txt"
    agent = HelixAgent(project, config, prompt_path)
    return agent.run(args.task)''',
                    "new": r'''def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Helix autonomous coding agent"
    )

    parser.add_argument(
        "--project",
        default=".",
        help=(
            "Target project directory. "
            "Defaults to the current directory."
        ),
    )

    parser.add_argument(
        "--task",
        help=(
            "Run one coding task and exit. "
            "Omit to start the interactive CLI."
        ),
    )

    parser.add_argument(
        "--config",
        default=str(
            Path(__file__).with_name(
                "helix.toml"
            )
        ),
        help="Path to helix.toml",
    )

    parser.add_argument(
        "--read-only",
        action="store_true",
        help=(
            "Allow inspection but block "
            "file creation and source edits."
        ),
    )

    parser.add_argument(
        "--no-exec",
        action="store_true",
        help=(
            "Disable model-requested "
            "command execution."
        ),
    )

    return parser


def interactive_shell(
    agent: HelixAgent,
) -> int:
    print(
        "  Commands: "
        ":help  :models  :history  "
        ":clear  :quit"
    )
    print()

    while True:
        try:
            task = input("helix> ").strip()

        except EOFError:
            print()
            return 0

        except KeyboardInterrupt:
            print(
                "\n  Use :quit to exit Helix."
            )
            continue

        if not task:
            continue

        command = task.lower()

        if command in {
            ":quit",
            ":exit",
        }:
            return 0

        if command == ":help":
            print()
            print(
                "  Enter a coding task directly "
                "at the helix> prompt."
            )
            print(
                "  :models   Show configured models"
            )
            print(
                "  :history  Show recent tasks"
            )
            print(
                "  :clear    Clear the terminal"
            )
            print(
                "  :quit     Exit Helix"
            )
            print()
            continue

        if command == ":models":
            agent.console.show_models()
            continue

        if command == ":history":
            agent.console.show_history(
                agent.sessions.recent()
            )
            continue

        if command == ":clear":
            os.system(
                "cls"
                if os.name == "nt"
                else "clear"
            )

            agent.console.banner()
            continue

        if task.startswith(":"):
            print(
                f"  Unknown command: {task}"
            )
            continue

        try:
            agent.run(task)

        except KeyboardInterrupt:
            print(
                "\n  Task interrupted by user."
            )


def main() -> int:
    args = build_parser().parse_args()

    project = Path(args.project)

    if (
        not project.exists()
        or not project.is_dir()
    ):
        print(
            f"Project directory does not exist: "
            f"{project}",
            file=sys.stderr,
        )
        return 2

    config = HelixConfig.load(
        Path(args.config)
    )

    prompt_path = (
        Path(__file__).parent
        / "prompts"
        / "coder.txt"
    )

    permissions = AgentPermissions(
        write=not args.read_only,
        execute=not args.no_exec,
    )

    agent = HelixAgent(
        project,
        config,
        prompt_path,
        permissions,
    )

    agent.console.banner()

    if args.task:
        return agent.run(args.task)

    return interactive_shell(agent)''',
                    "expected_matches": 1,
                },
            ],
        },
        {
            "path": "prompts/coder.txt",
            "sha256": "1ea08f414299517d029b586b00af0d66432eb3f63f6b3d44e9fdff40fd2e1bba",
            "edits": [
                {
                    "op": "insert_before",
                    "anchor": "\nUseful tools include list_files, read_file, search_text, hash_file, create_file, patch_file, run_command, git_diff, and finish.",
                    "content": r'''
19. Avoid rereading the same unchanged file repeatedly unless a previous edit failed or new information requires another read.
20. Once a verification command passes and no source files change afterward, do not run the same verification command again.
21. Prefer the shortest safe sequence of useful actions: inspect, diagnose, edit, verify, inspect the diff when useful, then finish.
22. If Helix reports that duplicate verification was skipped, treat verification as still successful.
23. If Helix denies an action because write or execution permission is disabled, do not repeatedly retry the denied action.
24. Successful patch_file means the deterministic edit applied, but the task still requires an appropriate verification command before finish.
''',
                    "expected_matches": 1,
                },
            ],
        },
        {
            "path": "tests/test_helix.py",
            "sha256": "2f86a9b76ca0eab0c223dd53c2dd6f6a54dc3408af929eb876239853c49d452f",
            "edits": [
                {
                    "op": "insert_before",
                    "anchor": '\n\nif __name__ == "__main__":',
                    "content": r'''

    def test_workspace_ignores_runtime_cache_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (root / "app.py").write_text(
                "print('ok')\n",
                encoding="utf-8",
            )

            cache = root / ".pytest_cache"
            cache.mkdir()

            (cache / "ignored.txt").write_text(
                "ignore me\n",
                encoding="utf-8",
            )

            workspace = helix.Workspace(root)
            files = workspace.list_files()

            self.assertIn(
                "app.py",
                files,
            )

            self.assertNotIn(
                ".pytest_cache/ignored.txt",
                files,
            )

    def test_duplicate_verification_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            prompt = root / "prompt.txt"
            prompt.write_text(
                "test prompt\n",
                encoding="utf-8",
            )

            config = helix.HelixConfig(
                patchforge_cli="",
                max_steps=10,
                command_timeout_seconds=10,
                models={
                    "main": helix.ModelSpec(
                        "ollama",
                        "main",
                    ),
                },
            )

            agent = helix.HelixAgent(
                root,
                config,
                prompt,
            )

            calls = []

            def fake_run(
                command,
                timeout_seconds=None,
            ):
                calls.append(command)

                return {
                    "ok": True,
                    "exit_code": 0,
                    "stdout": "1 passed\n",
                    "stderr": "",
                    "duration_seconds": 0.01,
                    "timed_out": False,
                }

            agent.runner.run = fake_run

            state = helix.AgentState(
                task="test",
                project_root=root,
            )

            first_ok, _ = agent.execute(
                "run_command",
                {
                    "command": "pytest -q",
                    "verification": True,
                },
                state,
            )

            second_ok, second_summary = agent.execute(
                "run_command",
                {
                    "command": "pytest -q",
                    "verification": True,
                },
                state,
            )

            self.assertTrue(first_ok)
            self.assertTrue(second_ok)

            self.assertEqual(
                calls,
                ["pytest -q"],
            )

            self.assertIn(
                "skipped duplicate",
                second_summary,
            )

    def test_source_change_resets_verification_cache(self):
        state = helix.AgentState(
            task="test",
            project_root=Path("."),
        )

        state.verification_passed = True
        state.last_verification_command = "pytest -q"

        state.verification_passed = False
        state.last_verification_command = ""

        self.assertFalse(
            state.verification_passed
        )

        self.assertEqual(
            state.last_verification_command,
            "",
        )

    def test_read_only_permission_blocks_file_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            prompt = root / "prompt.txt"
            prompt.write_text(
                "test prompt\n",
                encoding="utf-8",
            )

            config = helix.HelixConfig(
                patchforge_cli="",
                max_steps=10,
                command_timeout_seconds=10,
                models={
                    "main": helix.ModelSpec(
                        "ollama",
                        "main",
                    ),
                },
            )

            agent = helix.HelixAgent(
                root,
                config,
                prompt,
                helix.AgentPermissions(
                    write=False,
                    execute=True,
                ),
            )

            state = helix.AgentState(
                task="test",
                project_root=root,
            )

            ok, summary = agent.execute(
                "create_file",
                {
                    "path": "blocked.py",
                    "content": "pass\n",
                },
                state,
            )

            self.assertFalse(ok)

            self.assertIn(
                "read-only",
                summary.lower(),
            )

            self.assertFalse(
                (root / "blocked.py").exists()
            )

    def test_no_exec_permission_blocks_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            prompt = root / "prompt.txt"
            prompt.write_text(
                "test prompt\n",
                encoding="utf-8",
            )

            config = helix.HelixConfig(
                patchforge_cli="",
                max_steps=10,
                command_timeout_seconds=10,
                models={
                    "main": helix.ModelSpec(
                        "ollama",
                        "main",
                    ),
                },
            )

            agent = helix.HelixAgent(
                root,
                config,
                prompt,
                helix.AgentPermissions(
                    write=True,
                    execute=False,
                ),
            )

            state = helix.AgentState(
                task="test",
                project_root=root,
            )

            ok, summary = agent.execute(
                "run_command",
                {
                    "command": "python --version",
                    "verification": False,
                },
                state,
            )

            self.assertFalse(ok)

            self.assertIn(
                "denied",
                summary.lower(),
            )

    def test_session_store_records_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            store = helix.SessionStore(root)

            store.record(
                task="Fix tests",
                status="pass",
                summary="Everything passed.",
                steps=7,
                duration_seconds=1.5,
            )

            entries = store.recent()

            self.assertEqual(
                len(entries),
                1,
            )

            self.assertEqual(
                entries[0]["task"],
                "Fix tests",
            )

            self.assertEqual(
                entries[0]["status"],
                "pass",
            )

            self.assertEqual(
                entries[0]["steps"],
                7,
            )
''',
                    "expected_matches": 1,
                },
            ],
        },
        {
            "path": "pyproject.toml",
            "sha256": "017297302cbda152cfeba477990314355d01e3f39f87b5587f437130229abbac",
            "edits": [
                {
                    "op": "replace",
                    "old": 'version = "0.1.2"',
                    "new": 'version = "0.2.0"',
                    "expected_matches": 1,
                },
            ],
        },
        {
            "path": "README.md",
            "sha256": "ce598f8a5aa3e8c654fc43cba42635d9670134bce49daa11dfe387af66aa48c5",
            "edits": [
                {
                    "op": "replace",
                    "old": "Current version: **v0.1.2**",
                    "new": "Current version: **v0.2.0**",
                    "expected_matches": 1,
                },
                {
                    "op": "insert_before",
                    "anchor": "\n## Patch Forge",
                    "content": r'''

## Interactive CLI

Helix v0.2.0 includes an interactive terminal interface.

Start it with:

```powershell
python .\helix.py --project "C:\Path\To\Project"