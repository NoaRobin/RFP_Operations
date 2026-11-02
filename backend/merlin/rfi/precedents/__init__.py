"""Précédents : réponses déjà données dans d'anciens RFI, comparées aux données Fabric.

Trois couches séparées (règle du lot 02) :
  - la donnée   : la valeur Fabric du bon fonds, de la bonne part, à la bonne date (values.py) ;
  - le concept  : ce que la question demande (ontologie, ou liaison déduite d'un précédent vérifié dans Fabric) ;
  - la rédaction: le ton, la longueur, la langue et la structure d'une réponse historique (jamais ses valeurs).

Une réponse historique n'est jamais recopiée automatiquement : elle sert de preuve (« c'est ce qui a déjà été fait »),
de détecteur d'incohérence, ou de modèle de rédaction paramétré.
"""
from .model import Precedent
from .store import PrecedentStore

__all__ = ["Precedent", "PrecedentStore"]

from functools import lru_cache as _lru_cache
from pathlib import Path as _Path

from .retrieval import PrecedentIndex, default_embedder


def _onnx_encoder(models: _Path):
    """Encodeur E5 local s'il est installé (écran Qvidian › API & moteur) : même modèle que la recherche Qvidian."""
    try:
        from ...search import neural

        if not neural.available():
            return None
        for mid in ("e5-small", "e5-base"):
            if neural.installed(models, mid):
                return neural.Encoder(models, mid)
    except Exception:  # noqa: BLE001 - modèle abîmé : lexical seul
        return None
    return None


@_lru_cache
def get_index(root: _Path) -> PrecedentIndex:
    """Index unique par dossier de données (data/rfi/precedents.sqlite) ; encodeur E5 de data/models/ s'il existe."""
    return PrecedentIndex(PrecedentStore(root / "precedents.sqlite"), default_embedder(), _onnx_encoder(root.parent / "models"))


__all__ += ["PrecedentIndex", "get_index"]


@_lru_cache
def get_bindings(root: _Path):
    from .bindings import BindingIndex

    return BindingIndex(root / "bindings.json")


__all__ += ["get_bindings"]
