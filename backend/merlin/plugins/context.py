"""`ctx` : la boîte à outils partagée passée à chaque automatisation.

    def run(ctx, **params):
        ctx.log.info("Bonjour")
        with ctx.step("Extraction"):
            df = ctx.data.query("SELECT ... FROM dbo.JUMP_portfolio_aum WHERE DATE_VL = :d", {"d": params["date"]})
        ctx.show_table(df, "Aperçu")
        ctx.save_excel(df, "resultat.xlsx")

Le contexte s'exécute DANS le processus du job ; il communique avec Merlin via `emit`.
"""
from __future__ import annotations

import contextlib
import json
import re
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import pandas as pd

from ..data.access import DataAccess

Emit = Callable[[dict[str, Any]], None]


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def safe_filename(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w.\-]+", "_", name).strip("._")
    return name or "fichier"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if value != value else value  # NaN -> null
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return str(value)


def frame_preview(frame: pd.DataFrame, max_rows: int = 200) -> dict[str, Any]:
    head = frame.head(max_rows)
    return {
        "columns": [str(c) for c in head.columns],
        "rows": [[_jsonable(v) for v in row] for row in head.itertuples(index=False, name=None)],
        "total_rows": int(len(frame)),
    }


class RunLogger:
    def __init__(self, emit: Emit):
        self._emit = emit

    def _log(self, level: str, message: str, *args: Any) -> None:
        text = message % args if args else message
        self._emit({"type": "log", "level": level, "message": text, "ts": _now()})

    def debug(self, message: str, *args: Any) -> None:
        self._log("debug", message, *args)

    def info(self, message: str, *args: Any) -> None:
        self._log("info", message, *args)

    def success(self, message: str, *args: Any) -> None:
        self._log("success", message, *args)

    def warning(self, message: str, *args: Any) -> None:
        self._log("warning", message, *args)

    warn = warning

    def error(self, message: str, *args: Any) -> None:
        self._log("error", message, *args)


class BrowserNotAvailable(RuntimeError):
    pass


class BrowserSlot:
    """Emplacement réservé au futur navigateur Playwright.

    L'interface est figée dès maintenant pour que les automatisations puissent
    déclarer `requires: [browser]`. L'implémentation viendra plus tard :
    `async with ctx.browser.page() as page: ...`
    """

    available = False

    def page(self):
        raise BrowserNotAvailable(
            "Le navigateur automatisé n'est pas encore installé dans Merlin. "
            "Elle sera disponible avec l'intégration Playwright."
        )

    def __bool__(self) -> bool:
        return False


class RunContext:
    def __init__(
        self,
        *,
        job_id: str,
        user: str,
        params: dict[str, Any],
        output_dir: Path,
        data: DataAccess,
        emit: Emit,
        steps: list[str] | None = None,
    ):
        self.job_id = job_id
        self.user = user
        self.params = params
        self.output_dir = output_dir
        self.data = data
        self.log = RunLogger(emit)
        self.browser = BrowserSlot()
        self._emit = emit
        self._steps = steps or []
        self.summary: str | None = None
        self.metrics: dict[str, Any] = {}
        output_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- avancement
    @property
    def data_mode(self) -> str:
        return self.data.mode

    def progress(self, value: float, message: str | None = None) -> None:
        """value entre 0 et 1."""
        self._emit({"type": "progress", "value": max(0.0, min(1.0, float(value))), "message": message, "ts": _now()})

    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        index = self._steps.index(name) if name in self._steps else None
        self._emit({"type": "step", "name": name, "status": "running", "index": index, "ts": _now()})
        started = time.perf_counter()
        try:
            yield
        except Exception:
            self._emit({"type": "step", "name": name, "status": "error", "index": index, "ts": _now()})
            raise
        duration = round(time.perf_counter() - started, 2)
        self._emit({"type": "step", "name": name, "status": "done", "index": index, "duration": duration, "ts": _now()})
        if self._steps and index is not None:
            self.progress((index + 1) / len(self._steps))

    # ---------------------------------------------------------------- sorties
    def register_file(self, path: Path, kind: str = "file", label: str | None = None) -> Path:
        """Déclare un fichier déjà écrit dans output_dir comme sortie téléchargeable."""
        self._emit({
            "type": "output", "name": path.name, "kind": kind, "label": label or path.name,
            "size": path.stat().st_size, "ts": _now(),
        })
        return path

    def save_excel(
        self,
        frames: pd.DataFrame | dict[str, pd.DataFrame],
        filename: str,
        *,
        number_formats: dict[str, str] | None = None,
        label: str | None = None,
    ) -> Path:
        from ..atelier.writer import write_frames_to_excel

        if not filename.lower().endswith((".xlsx", ".xlsm")):
            filename += ".xlsx"
        path = self.output_dir / safe_filename(filename)
        sheets = frames if isinstance(frames, dict) else {"Résultat": frames}
        write_frames_to_excel(sheets, path, number_formats or {})
        return self.register_file(path, "excel", label)

    def save_csv(self, frame: pd.DataFrame, filename: str, *, label: str | None = None) -> Path:
        path = self.output_dir / safe_filename(filename if filename.endswith(".csv") else filename + ".csv")
        frame.to_csv(path, index=False, sep=";", encoding="utf-8-sig", decimal=",")
        return self.register_file(path, "csv", label)

    def save_file(self, filename: str, content: bytes | str, *, label: str | None = None) -> Path:
        path = self.output_dir / safe_filename(filename)
        if isinstance(content, str):
            path.write_text(content, encoding="utf-8")
        else:
            path.write_bytes(content)
        return self.register_file(path, "file", label)

    def show_table(self, frame: pd.DataFrame, title: str = "Aperçu", max_rows: int = 200) -> None:
        self._emit({"type": "table", "title": title, **frame_preview(frame, max_rows), "ts": _now()})

    def set_summary(self, text: str, **metrics: Any) -> None:
        self.summary = text
        self.metrics.update({k: _jsonable(v) for k, v in metrics.items()})
        self._emit({"type": "summary", "text": text, "metrics": json.loads(json.dumps(self.metrics, default=str)), "ts": _now()})
