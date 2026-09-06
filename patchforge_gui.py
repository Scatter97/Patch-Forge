from __future__ import annotations

import json
import sys
import traceback

from pathlib import Path

from PySide6.QtCore import (
    QThread,
    Signal,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

import patchforge


APP_STYLE = """
QWidget {
    background: #101217;
    color: #E8EAF0;
    font-family: "Segoe UI";
    font-size: 10pt;
}

QMainWindow {
    background: #101217;
}

QFrame#Sidebar,
QFrame#Pipeline {
    background: #151820;
    border: 1px solid #242936;
    border-radius: 12px;
}

QLineEdit,
QPlainTextEdit,
QListWidget {
    background: #0C0E13;
    border: 1px solid #2A3040;
    border-radius: 8px;
    padding: 7px;
    selection-background-color: #375A9E;
}

QLineEdit:focus,
QPlainTextEdit:focus,
QListWidget:focus {
    border: 1px solid #5A7FD0;
}

QPushButton {
    background: #202634;
    border: 1px solid #30384A;
    border-radius: 8px;
    padding: 8px 13px;
    min-height: 20px;
}

QPushButton:hover {
    background: #293144;
}

QPushButton:pressed {
    background: #1A2030;
}

QPushButton#Primary {
    background: #4B6FBF;
    border: 1px solid #6285D0;
    font-weight: 600;
}

QPushButton#Primary:hover {
    background: #567AC8;
}

QPushButton#Danger {
    background: #612F38;
    border: 1px solid #82424D;
}

QTabWidget::pane {
    border: 1px solid #252A36;
    border-radius: 8px;
}

QTabBar::tab {
    background: #171A22;
    padding: 9px 16px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #262C3A;
}

QLabel#Title {
    font-size: 20pt;
    font-weight: 700;
}

QLabel#Subtitle {
    color: #9299AA;
}

QLabel#StatusPending {
    color: #9299AA;
}

QLabel#StatusPass {
    color: #72D69C;
    font-weight: 600;
}

QLabel#StatusFail {
    color: #FF7C88;
    font-weight: 600;
}
"""


class DiffHighlighter(
    QSyntaxHighlighter
):
    def __init__(self, document):
        super().__init__(
            document
        )

        self.added = QTextCharFormat()
        self.added.setForeground(
            QColor("#73D69C")
        )

        self.removed = QTextCharFormat()
        self.removed.setForeground(
            QColor("#FF818C")
        )

        self.header = QTextCharFormat()
        self.header.setForeground(
            QColor("#8AB4F8")
        )

        self.hunk = QTextCharFormat()
        self.hunk.setForeground(
            QColor("#C5A3FF")
        )

    def highlightBlock(
        self,
        text: str,
    ) -> None:
        if text.startswith("+++") or text.startswith("---"):
            self.setFormat(
                0,
                len(text),
                self.header,
            )

        elif text.startswith("+"):
            self.setFormat(
                0,
                len(text),
                self.added,
            )

        elif text.startswith("-"):
            self.setFormat(
                0,
                len(text),
                self.removed,
            )

        elif text.startswith("@@"):
            self.setFormat(
                0,
                len(text),
                self.hunk,
            )

        elif text.startswith("diff --git"):
            self.setFormat(
                0,
                len(text),
                self.header,
            )


class Worker(
    QThread
):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        function,
    ):
        super().__init__()

        self.function = function

    def run(self) -> None:
        try:
            result = self.function()

            self.completed.emit(
                result
            )

        except Exception as exc:
            message = (
                f"{exc}\n\n"
                f"{traceback.format_exc()}"
            )

            self.failed.emit(
                message
            )


class PatchForgeWindow(
    QMainWindow
):
    def __init__(self):
        super().__init__()

        self.repo: Path | None = None
        self.patch_path: Path | None = None
        self.worker: Worker | None = None

        self.setWindowTitle(
            "Patch Forge"
        )

        self.resize(
            1500,
            900,
        )

        self.build_ui()

    def build_ui(self) -> None:
        root = QWidget()

        outer = QVBoxLayout(
            root
        )

        outer.setContentsMargins(
            18,
            18,
            18,
            18,
        )

        title = QLabel(
            "Patch Forge"
        )

        title.setObjectName(
            "Title"
        )

        subtitle = QLabel(
            "Deterministic source patching, "
            "validation and verification"
        )

        subtitle.setObjectName(
            "Subtitle"
        )

        outer.addWidget(
            title
        )

        outer.addWidget(
            subtitle
        )

        selector = QHBoxLayout()

        self.repo_edit = QLineEdit()
        self.repo_edit.setPlaceholderText(
            "Repository directory"
        )

        repo_button = QPushButton(
            "Browse Repo"
        )

        repo_button.clicked.connect(
            self.choose_repo
        )

        self.patch_edit = QLineEdit()
        self.patch_edit.setPlaceholderText(
            "Patch JSON"
        )

        patch_button = QPushButton(
            "Open Patch"
        )

        patch_button.clicked.connect(
            self.choose_patch
        )

        selector.addWidget(
            QLabel("Repository")
        )

        selector.addWidget(
            self.repo_edit,
            3,
        )

        selector.addWidget(
            repo_button
        )

        selector.addSpacing(
            14
        )

        selector.addWidget(
            QLabel("Patch")
        )

        selector.addWidget(
            self.patch_edit,
            3,
        )

        selector.addWidget(
            patch_button
        )

        outer.addLayout(
            selector
        )

        splitter = QSplitter(
            Qt.Horizontal
        )

        splitter.addWidget(
            self.build_sidebar()
        )

        splitter.addWidget(
            self.build_main_tabs()
        )

        splitter.addWidget(
            self.build_pipeline()
        )

        splitter.setStretchFactor(
            0,
            0,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        splitter.setStretchFactor(
            2,
            0,
        )

        splitter.setSizes(
            [210, 1000, 260]
        )

        outer.addWidget(
            splitter,
            1,
        )

        self.setCentralWidget(
            root
        )

    def build_sidebar(self) -> QWidget:
        frame = QFrame()

        frame.setObjectName(
            "Sidebar"
        )

        layout = QVBoxLayout(
            frame
        )

        layout.addWidget(
            QLabel("Actions")
        )

        validate = QPushButton(
            "Validate / Dry Run"
        )

        validate.clicked.connect(
            self.validate_patch
        )

        run = QPushButton(
            "Run Patch"
        )

        run.setObjectName(
            "Primary"
        )

        run.clicked.connect(
            self.run_patch
        )

        diff = QPushButton(
            "Refresh Diff"
        )

        diff.clicked.connect(
            self.refresh_diff
        )

        verify = QPushButton(
            "Run Verification"
        )

        verify.clicked.connect(
            self.run_verify
        )

        hash_button = QPushButton(
            "File SHA-256"
        )

        hash_button.clicked.connect(
            self.show_hash
        )

        checkpoints = QPushButton(
            "Refresh Checkpoints"
        )

        checkpoints.clicked.connect(
            self.refresh_checkpoints
        )

        rollback = QPushButton(
            "Rollback Selected"
        )

        rollback.setObjectName(
            "Danger"
        )

        rollback.clicked.connect(
            self.rollback_selected
        )

        save = QPushButton(
            "Save JSON"
        )

        save.clicked.connect(
            self.save_patch
        )

        for button in (
            validate,
            run,
            diff,
            verify,
            hash_button,
            checkpoints,
            rollback,
            save,
        ):
            layout.addWidget(
                button
            )

        layout.addStretch(
            1
        )

        return frame

    def build_main_tabs(self) -> QWidget:
        self.tabs = QTabWidget()

        self.json_editor = QPlainTextEdit()

        font = QFont(
            "Cascadia Mono"
        )

        font.setStyleHint(
            QFont.Monospace
        )

        self.json_editor.setFont(
            font
        )

        self.diff_editor = QPlainTextEdit()
        self.diff_editor.setReadOnly(
            True
        )

        self.diff_editor.setFont(
            font
        )

        self.proposed_diff_editor = QPlainTextEdit()
        self.proposed_diff_editor.setReadOnly(
            True
        )
        self.proposed_diff_editor.setFont(
            font
        )

        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(
            True
        )

        self.output_editor.setFont(
            font
        )

        self.checkpoint_list = QListWidget()

        DiffHighlighter(
            self.diff_editor.document()
        )

        DiffHighlighter(
            self.proposed_diff_editor.document()
        )

        self.tabs.addTab(
            self.json_editor,
            "Patch JSON",
        )

        self.tabs.addTab(
            self.proposed_diff_editor,
            "Proposed Diff",
        )

        self.tabs.addTab(
            self.diff_editor,
            "Repository Diff",
        )

        self.tabs.addTab(
            self.output_editor,
            "Output",
        )

        self.tabs.addTab(
            self.checkpoint_list,
            "Checkpoints",
        )

        return self.tabs

    def build_pipeline(self) -> QWidget:
        frame = QFrame()

        frame.setObjectName(
            "Pipeline"
        )

        layout = QVBoxLayout(
            frame
        )

        layout.addWidget(
            QLabel("Pipeline")
        )

        self.status_preflight = QLabel()
        self.status_dryrun = QLabel()
        self.status_apply = QLabel()
        self.status_build = QLabel()
        self.status_verify = QLabel()
        self.status_tests = QLabel()

        self.pipeline_labels = [
            (
                "Preflight",
                self.status_preflight,
            ),
            (
                "Dry run",
                self.status_dryrun,
            ),
            (
                "Apply",
                self.status_apply,
            ),
            (
                "Build",
                self.status_build,
            ),
            (
                "Verification",
                self.status_verify,
            ),
            (
                "Tests",
                self.status_tests,
            ),
        ]

        for name, label in self.pipeline_labels:
            layout.addWidget(
                QLabel(name)
            )

            layout.addWidget(
                label
            )

        layout.addStretch(
            1
        )

        self.reset_pipeline()

        return frame

    def reset_pipeline(self) -> None:
        for _, label in self.pipeline_labels:
            label.setText(
                "● Pending"
            )

            label.setObjectName(
                "StatusPending"
            )

            label.style().unpolish(
                label
            )

            label.style().polish(
                label
            )

    def set_status(
        self,
        label: QLabel,
        passed: bool,
        text: str,
    ) -> None:
        label.setText(
            (
                "✓ "
                if passed
                else
                "✕ "
            )
            +
            text
        )

        label.setObjectName(
            (
                "StatusPass"
                if passed
                else
                "StatusFail"
            )
        )

        label.style().unpolish(
            label
        )

        label.style().polish(
            label
        )

    def choose_repo(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Repository",
        )

        if not directory:
            return

        try:
            self.repo = patchforge.normalize_repo(
                directory
            )

            self.repo_edit.setText(
                str(self.repo)
            )

            self.append_output(
                f"Repository: {self.repo}"
            )

            self.refresh_diff()
            self.refresh_checkpoints()

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def choose_patch(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Patch JSON",
            "",
            "JSON files (*.json);;All files (*)",
        )

        if not filename:
            return

        self.patch_path = Path(
            filename
        ).resolve()

        self.patch_edit.setText(
            str(self.patch_path)
        )

        try:
            text = self.patch_path.read_text(
                encoding="utf-8"
            )

            self.json_editor.setPlainText(
                text
            )

            self.append_output(
                f"Loaded patch: {self.patch_path}"
            )

            self.reset_pipeline()

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def save_patch(self) -> None:
        if self.patch_path is None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Patch JSON",
                "",
                "JSON files (*.json)",
            )

            if not filename:
                return

            self.patch_path = Path(
                filename
            ).resolve()

            self.patch_edit.setText(
                str(self.patch_path)
            )

        try:
            spec = patchforge.parse_json_text(
                self.json_editor.toPlainText()
            )

            formatted = json.dumps(
                spec,
                indent=2,
            )

            self.patch_path.write_text(
                formatted + "\n",
                encoding="utf-8",
            )

            self.json_editor.setPlainText(
                formatted
            )

            self.append_output(
                f"Saved: {self.patch_path}"
            )

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def current_repo(self) -> Path:
        value = self.repo_edit.text().strip()

        if not value:
            raise patchforge.PatchForgeError(
                "Choose a repository first."
            )

        self.repo = patchforge.normalize_repo(
            value
        )

        return self.repo

    def current_spec(self):
        return patchforge.parse_json_text(
            self.json_editor.toPlainText()
        )

    def set_busy(
        self,
        busy: bool,
    ) -> None:
        self.setEnabled(
            not busy
        )

    def launch(
        self,
        function,
        success,
    ) -> None:
        self.set_busy(
            True
        )

        worker = Worker(
            function
        )

        self.worker = worker

        worker.completed.connect(
            success
        )

        worker.completed.connect(
            lambda _: self.set_busy(False)
        )

        worker.failed.connect(
            self.worker_failed
        )

        worker.failed.connect(
            lambda _: self.set_busy(False)
        )

        worker.start()

    def worker_failed(
        self,
        message: str,
    ) -> None:
        self.append_output(
            "FAILED\n" + message
        )

        self.show_error(
            message.split(
                "\n\n",
                1,
            )[0]
        )

    def validate_patch(self) -> None:
        try:
            repo = self.current_repo()
            spec = self.current_spec()

        except Exception as exc:
            self.show_error(
                str(exc)
            )
            return

        self.reset_pipeline()

        self.append_output(
            "Starting validation..."
        )

        def job():
            preflight = patchforge.run_preflight(
                repo,
                spec,
            )

            prepared = patchforge.prepare_patch(
                repo,
                spec,
            )

            proposed = patchforge.proposed_diff_text(
                prepared
            )

            return (
                preflight,
                prepared,
                proposed,
            )

        def done(result):
            preflight, prepared, proposed = result

            self.set_status(
                self.status_preflight,
                True,
                (
                    f"Passed "
                    f"({len(preflight)} checks)"
                ),
            )

            self.set_status(
                self.status_dryrun,
                True,
                (
                    f"Passed "
                    f"({len(prepared)} files)"
                ),
            )

            self.proposed_diff_editor.setPlainText(
                (
                    proposed
                    if proposed
                    else
                    "No textual changes."
                )
            )

            self.tabs.setCurrentWidget(
                self.proposed_diff_editor
            )

            lines = [
                "Validation PASSED.",
                "Proposed diff generated without writing files.",
                "",
            ]

            for item in prepared:
                lines.extend(
                    [
                        item.relative_path,
                        (
                            "  old: "
                            f"{item.original_sha256}"
                        ),
                        (
                            "  new: "
                            f"{item.new_sha256}"
                        ),
                    ]
                )

            self.append_output(
                "\n".join(lines)
            )

            self.refresh_diff()

        self.launch(
            job,
            done,
        )

    def run_patch(self) -> None:
        try:
            repo = self.current_repo()
            spec = self.current_spec()

        except Exception as exc:
            self.show_error(
                str(exc)
            )
            return

        answer = QMessageBox.question(
            self,
            "Run Patch",
            (
                "Patch Forge will run preflight checks, "
                "perform a deterministic dry run, create "
                "a checkpoint, apply the patch, run any "
                "configured build commands, verification "
                "checks, and tests.\n\nContinue?"
            ),
        )

        if answer != QMessageBox.Yes:
            return

        self.reset_pipeline()

        self.append_output(
            "Running full patch workflow..."
        )

        def job():
            return patchforge.run_workflow(
                repo,
                spec,
            )

        def done(result):
            self.set_status(
                self.status_preflight,
                True,
                "Passed",
            )

            self.set_status(
                self.status_dryrun,
                True,
                "Passed",
            )

            self.set_status(
                self.status_apply,
                True,
                "Applied",
            )

            self.set_status(
                self.status_build,
                True,
                (
                    f"Passed ({len(result.build)} commands)"
                    if result.build
                    else
                    "Not configured"
                ),
            )

            self.set_status(
                self.status_verify,
                True,
                (
                    f"Passed "
                    f"({len(result.verify)} checks)"
                ),
            )

            self.set_status(
                self.status_tests,
                True,
                (
                    f"Passed ({len(result.tests)} tests)"
                    if result.tests
                    else
                    "Not configured"
                ),
            )

            self.append_output(
                "Patch Forge workflow PASSED."
            )

            if result.checkpoint:
                self.append_output(
                    "Checkpoint: "
                    f"{result.checkpoint.name}"
                )

            for check in result.build:
                self.append_output(
                    f"[BUILD PASS] {check.name}"
                )

                if check.output:
                    self.append_output(
                        check.output.rstrip()
                    )

            for check in result.verify:
                self.append_output(
                    f"[PASS] {check.name}"
                )

                if check.output:
                    self.append_output(
                        check.output.rstrip()
                    )

            for check in result.tests:
                self.append_output(
                    f"[TEST PASS] {check.name}"
                )

                if check.output:
                    self.append_output(
                        check.output.rstrip()
                    )

            self.refresh_diff()
            self.refresh_checkpoints()

            QMessageBox.information(
                self,
                "Patch Forge",
                "Patch workflow passed.",
            )

        self.launch(
            job,
            done,
        )

    def run_verify(self) -> None:
        try:
            repo = self.current_repo()
            spec = self.current_spec()

        except Exception as exc:
            self.show_error(
                str(exc)
            )
            return

        self.append_output(
            "Running verification..."
        )

        def job():
            return patchforge.run_verification(
                repo,
                spec,
            )

        def done(results):
            self.set_status(
                self.status_verify,
                True,
                (
                    f"Passed "
                    f"({len(results)} checks)"
                ),
            )

            for result in results:
                self.append_output(
                    f"[PASS] {result.name}"
                )

                if result.output:
                    self.append_output(
                        result.output.rstrip()
                    )

        self.launch(
            job,
            done,
        )

    def refresh_diff(self) -> None:
        try:
            repo = self.current_repo()

        except Exception:
            return

        def job():
            patchforge.git_diff_check(
                repo
            )

            return patchforge.git_diff_text(
                repo
            )

        def done(text):
            self.diff_editor.setPlainText(
                (
                    text
                    if text
                    else
                    "No tracked changes."
                )
            )

        self.launch(
            job,
            done,
        )

    def refresh_checkpoints(self) -> None:
        try:
            repo = self.current_repo()

        except Exception:
            return

        try:
            checkpoints = (
                patchforge.list_checkpoints(
                    repo
                )
            )

            self.checkpoint_list.clear()

            for checkpoint in reversed(
                checkpoints
            ):
                manifest = (
                    patchforge
                    .load_checkpoint_manifest(
                        checkpoint
                    )
                )

                label = manifest.get(
                    "label"
                )

                display = checkpoint.name

                if label:
                    display += (
                        "   —   "
                        + str(label)
                    )

                self.checkpoint_list.addItem(
                    display
                )

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def rollback_selected(self) -> None:
        try:
            repo = self.current_repo()

        except Exception as exc:
            self.show_error(
                str(exc)
            )
            return

        item = self.checkpoint_list.currentItem()

        if item is None:
            self.show_error(
                "Select a checkpoint first."
            )
            return

        checkpoint_id = (
            item.text()
            .split(
                "   —   ",
                1,
            )[0]
        )

        answer = QMessageBox.warning(
            self,
            "Rollback",
            (
                "Restore files from checkpoint:\n\n"
                f"{checkpoint_id}\n\n"
                "Continue?"
            ),
            QMessageBox.Yes |
            QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        try:
            checkpoint = (
                patchforge.find_checkpoint(
                    repo,
                    checkpoint_id,
                )
            )

            patchforge.restore_checkpoint(
                repo,
                checkpoint,
            )

            self.append_output(
                "Rolled back: "
                f"{checkpoint_id}"
            )

            self.refresh_diff()

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def show_hash(self) -> None:
        try:
            repo = self.current_repo()

        except Exception as exc:
            self.show_error(
                str(exc)
            )
            return

        relative, ok = QInputDialog.getText(
            self,
            "File SHA-256",
            "Repository-relative path:",
        )

        if not ok or not relative.strip():
            return

        try:
            path = patchforge.resolve_repo_path(
                repo,
                relative.strip(),
            )

            if not path.is_file():
                raise patchforge.PatchForgeError(
                    f"File not found: {relative}"
                )

            digest = patchforge.sha256_bytes(
                path.read_bytes()
            )

            self.append_output(
                f"{relative.strip()}\n{digest}"
            )

            QMessageBox.information(
                self,
                "SHA-256",
                digest,
            )

        except Exception as exc:
            self.show_error(
                str(exc)
            )

    def append_output(
        self,
        text: str,
    ) -> None:
        self.output_editor.appendPlainText(
            text
        )

        self.tabs.setCurrentWidget(
            self.output_editor
        )

    def show_error(
        self,
        text: str,
    ) -> None:
        QMessageBox.critical(
            self,
            "Patch Forge",
            text,
        )


def main() -> int:
    application = QApplication(
        sys.argv
    )

    application.setApplicationName(
        "Patch Forge"
    )

    application.setStyleSheet(
        APP_STYLE
    )

    window = PatchForgeWindow()

    window.show()

    return application.exec()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )