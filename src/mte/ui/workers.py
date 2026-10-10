"""Background loading/saving so large folders don't freeze the UI."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.batch import BatchResult, save_all
from ..core.scanner import find_audio_files, has_audio_ext
from ..core.tagfile import load


class LoadSignals(QObject):
    loaded = Signal(list)          # list[FileTags]
    progress = Signal(int, int)    # done, total
    finished = Signal()


class LoadWorker(QRunnable):
    CHUNK = 25

    def __init__(self, paths: list[str], skip: set[str] | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.skip = skip or set()
        self.signals = LoadSignals()
        self.cancelled = False

    def run(self) -> None:
        files: list[str] = []
        for p in self.paths:
            if os.path.isdir(p):
                files.extend(find_audio_files(p))
            elif os.path.isfile(p) and has_audio_ext(p):
                files.append(p)
        files = [os.path.normpath(f) for f in files]
        files = [f for f in dict.fromkeys(files) if f not in self.skip]
        total = len(files)
        chunk = []
        for i, path in enumerate(files):
            if self.cancelled:
                break
            chunk.append(load(path))
            if len(chunk) >= self.CHUNK:
                self.signals.loaded.emit(chunk)
                chunk = []
                self.signals.progress.emit(i + 1, total)
        if chunk:
            self.signals.loaded.emit(chunk)
        self.signals.progress.emit(total, total)
        self.signals.finished.emit()


class SaveSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)      # BatchResult


class SaveWorker(QRunnable):
    def __init__(self, plan, naming=None) -> None:
        super().__init__()
        self.plan = plan
        self.naming = naming
        self.signals = SaveSignals()

    def run(self) -> None:
        try:
            result = save_all(self.plan, progress=self.signals.progress.emit,
                              naming=self.naming)
        except Exception as e:  # pragma: no cover - save_all already catches per file
            result = BatchResult(errors={"<batch>": str(e)})
        self.signals.finished.emit(result)
