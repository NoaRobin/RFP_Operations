"""Construction, apprentissage et partage du rapprochement de questions pour un instantané Qvidian.

Un seul moteur par instantané (`MATCHERS`) : la recherche Qvidian, les suggestions Qvidian du compléteur RFI et l'API
`/api/qvidian/match` lisent le même objet. Construit en arrière-plan (jamais pendant une requête) ; le modèle appris
est gardé sur disque (`<instantané>.matcher.json`) et n'est réappris que si les anciens RFI ou les modèles changent.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .gbdt import CalibratedModel
from .matcher import QuestionMatcher, build_bank

MATCHERS: dict[str, QuestionMatcher] = {}


def concept_function() -> Callable[[str], tuple[str, float] | None] | None:
    """Concept de l'ontologie RFI d'une question (le sens seul ne suffit jamais : le concept départage)."""
    try:
        from ..config import get_settings
        from ..data.catalog import load_catalog
        from ..rfi.match import match
        from ..rfi.ontology import load_ontology
        from ..rfi.understand import understand

        onto = load_ontology(load_catalog(str(get_settings().catalog_csv)))

        def concept_of(text: str):
            found = match(onto, understand(onto, text), limit=1)
            return (found[0].concept.id, found[0].score) if found and found[0].score >= 0.5 else None
        return concept_of
    except Exception:  # noqa: BLE001
        return None


class MatchBuilder:
    def __init__(self):
        self.state: dict[str, Any] = {"running": False, "message": "", "error": None, "built_at": None}
        self._lock = threading.Lock()

    def get(self, snapshot_path: Path) -> QuestionMatcher | None:
        return MATCHERS.get(str(snapshot_path))

    def build(self, snapshot, precedents: list[Any], links: list[Any], models: dict[str, Any], signature: str,
              background: bool = True) -> dict[str, Any]:
        with self._lock:
            if self.state["running"]:
                return self.state
            self.state.update(running=True, message="Banque des questions déjà tombées…", error=None)

        def run() -> None:
            try:
                t0 = time.time()
                contents = snapshot.all()
                entries = build_bank(precedents, contents, links)
                enc = models.get("encoder")
                vectors = None
                if enc is not None:
                    from ..search.neural import VectorCache

                    vectors = VectorCache(snapshot.path.with_name(f"{snapshot.path.stem}.questions.{enc.id}.npz"))
                self.state["message"] = f"{len(entries)} questions distinctes : index et vecteurs…"
                m = QuestionMatcher(entries, enc, models.get("reranker"), models.get("precise_encoder"), models.get("precise_reranker"),
                                    concept_function(), vectors=vectors)
                model_path = snapshot.path.with_name(f"{snapshot.path.stem}.matcher.json")
                sig = f"{signature}|{len(entries)}|" + "|".join(getattr(models.get(k), "id", "-") for k in
                                                               ("encoder", "reranker", "precise_encoder", "precise_reranker"))
                saved = _load(model_path)
                if saved and saved.get("signature") == sig:
                    m.fast_model = CalibratedModel.from_dict(saved["fast"]) if saved.get("fast") else None
                    m.precise_model = CalibratedModel.from_dict(saved["precise"]) if saved.get("precise") else None
                    trained = saved.get("trained", {})
                else:
                    self.state["message"] = "Apprentissage sur les anciens RFI (couples de questions étiquetés par les réponses choisies)…"
                    by_id = {c["id"]: c.get("text") or "" for c in contents}
                    trained = m.train(lambda cid: by_id.get(cid, ""))
                    _save(model_path, {"signature": sig, "trained": {k: v for k, v in trained.items() if k not in ("fast", "precise")},
                                       "fast": m.fast_model.to_dict() if m.fast_model else None,
                                       "precise": m.precise_model.to_dict() if m.precise_model else None})
                MATCHERS[str(snapshot.path)] = m
                self.state.update(running=False, message="Prêt.", built_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                  seconds=round(time.time() - t0, 1), trained=trained.get("trained", m.fast_model is not None),
                                  reason=trained.get("reason", ""))
            except Exception as error:  # noqa: BLE001 - le rapprochement ne bloque jamais la recherche
                self.state.update(running=False, error=str(error)[:300], message="")

        if background:
            threading.Thread(target=run, name="question-matcher", daemon=True).start()
        else:
            run()
        return self.state


def _load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


__all__ = ["MATCHERS", "MatchBuilder", "concept_function"]
