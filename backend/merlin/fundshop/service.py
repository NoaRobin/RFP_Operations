"""Assemblage : mémoire, liste, résolveur, dossier de destination (selon la configuration)."""
from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..data.access import DataAccess
from .memory import Memory
from .resolver import Resolver
from .shopping import ShoppingList


def root(settings: Settings) -> Path:
    return settings.data_dir / "fundshop"


def destination(settings: Settings) -> Path:
    return Path(settings.fundshop.dest_dir) if settings.fundshop.dest_dir else root(settings) / "documents"


def shopping_list(settings: Settings) -> ShoppingList:
    return ShoppingList(root(settings) / "list.json")


def memory(settings: Settings) -> Memory:
    return Memory(root(settings) / "learned.json")


def resolver(settings: Settings, data: DataAccess | None) -> Resolver:
    return Resolver(data, memory(settings), docs_base=settings.fundshop.docs_base, site_base=settings.fundshop.site_base)
