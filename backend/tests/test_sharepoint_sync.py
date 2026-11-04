"""Synchronisation SharePoint complète : arrière-plan, incrémentale, homonymes distincts, erreurs passagères reprises,
chaque échec expliqué, chemins longs sans casse."""
import time

from openpyxl import Workbook

from merlin.rfi.precedents.importers import import_document
from merlin.rfi.precedents.store import PrecedentStore
from merlin.rfi.sources.base import SourceError
from merlin.rfi.sources.local import LocalFolderSource
from merlin.rfi.sources.sync import SharePointSync, cache_name, retry


def _ddq(path, company):
    wb = Workbook()
    ws = wb.active
    ws.append(["Question", "Réponse"])
    ws.append(["Société de gestion", company])
    ws.append(["Is the fund UCITS compliant?", "Yes"])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _tree(tmp_path):
    root = tmp_path / "Due diligence"
    _ddq(root / "2026" / "RFI" / "DD Assureur Imaginaire" / "Final" / "DDQ.xlsx", "Gestion Fictive A")
    _ddq(root / "2025" / "RFI" / "DD Banque Fictive" / "Fonds Imaginaire" / "final" / "DDQ.xlsx", "Gestion Fictive B")
    _ddq(root / "2025" / "RFI" / "DD Caisse Fictive" / "Final" / ("Q" * 120 + ".xlsx"), "Gestion Fictive C")
    (root / "2025" / "RFI" / "DD Vide" / "Travail").mkdir(parents=True)
    return root


class Flaky(LocalFolderSource):
    """Premier téléchargement de chaque fichier refusé « à réessayer » (fichier OneDrive pas encore descendu)."""

    def __init__(self, root):
        super().__init__(root)
        self.seen = set()

    def download(self, item, target):
        if item.path not in self.seen:
            self.seen.add(item.path)
            raise SourceError(f"{item.name} : copie impossible.", "pas encore descendu", transient=True, retry_after=0.01)
        return super().download(item, target)


def _wait(sync):
    for _ in range(400):
        if not sync.state.get("running"):
            return sync.status()
        time.sleep(0.02)
    raise AssertionError("synchronisation bloquée")


def test_full_sync_is_incremental_keeps_homonyms_and_retries(tmp_path):
    root = _tree(tmp_path)
    store = PrecedentStore(tmp_path / "p.sqlite")
    done = []
    importer = lambda path, item, key: import_document(store, path, "sharepoint", display_name=key, modified=item.modified)  # noqa: E731
    sync = SharePointSync(tmp_path / "sp", importer, on_done=lambda: done.append(1))
    st = _wait(sync) if sync.start(Flaky(root)) else None
    assert st["found"] == 3 and st["failed"] == 0 and st["done"] == 3 and done == [1], st
    files = {p.source_file for p in store.all()}
    assert len([f for f in files if f.endswith("/DDQ.xlsx")]) == 2  # deux « DDQ.xlsx » de deux clients : les deux gardés
    assert {p.answer_raw for p in store.all()} >= {"Gestion Fictive A", "Gestion Fictive B", "Gestion Fictive C"}
    assert all(len(p.name) < 40 for p in (tmp_path / "sp" / "files").iterdir())  # copies locales à nom court
    st = _wait(sync) if sync.start(LocalFolderSource(root)) else None
    assert st["skipped"] == 3 and st.get("todo") == 0  # rien de nouveau : rien n'est relu
    _ddq(root / "2026" / "RFI" / "DD Nouveau Client" / "Final" / "RFI.xlsx", "Gestion Fictive D")
    st = _wait(sync) if sync.start(LocalFolderSource(root)) else None
    assert st["todo"] == 1 and st["corpus"]["documents"] == 4


def test_errors_are_explained_and_do_not_stop_the_others(tmp_path):
    root = _tree(tmp_path)
    (root / "2025" / "RFI" / "DD Banque Fictive" / "Fonds Imaginaire" / "final" / "DDQ.xlsx").write_bytes(b"pas un classeur")
    store = PrecedentStore(tmp_path / "p.sqlite")
    sync = SharePointSync(tmp_path / "sp", lambda path, item, key: import_document(store, path, "sharepoint", display_name=key))
    sync.start(LocalFolderSource(root))
    st = _wait(sync)
    assert st["failed"] == 1 and st["done"] == 3 and "DDQ.xlsx" in st["errors"][0]["file"]
    assert sync.manifest()[st["errors"][0]["file"]]["ok"] is False


def test_retry_only_retries_passing_errors():
    calls = []

    def boom():
        calls.append(1)
        raise SourceError("Accès refusé")
    try:
        retry(boom, sleep=lambda s: None)
    except SourceError:
        pass
    assert calls == [1]
    assert cache_name("a/b/c.XLSX").endswith(".xlsx") and len(cache_name("x" * 500)) < 30
