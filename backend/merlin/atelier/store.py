"""Stockage de l'Atelier : classeurs déposés (jamais modifiés), versions générées, recettes YAML."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ALLOWED_SUFFIXES = {".xlsx", ".xlsm"}


class AtelierStore:
    def __init__(self, root: Path):
        self.root = root
        self.workbooks = root / "workbooks"
        self.recipes = root / "recipes"
        self.workbooks.mkdir(parents=True, exist_ok=True)
        self.recipes.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- classeurs
    def workbook_dir(self, workbook_id: str) -> Path:
        if not re.fullmatch(r"wb_[a-f0-9]{12}", workbook_id):
            raise FileNotFoundError(workbook_id)
        path = self.workbooks / workbook_id
        if not path.exists():
            raise FileNotFoundError(workbook_id)
        return path

    def save_upload(self, filename: str, content: bytes, user: str) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError(suffix)
        workbook_id = f"wb_{uuid.uuid4().hex[:12]}"
        folder = self.workbooks / workbook_id
        (folder / "versions").mkdir(parents=True)
        original = folder / f"original{suffix}"
        original.write_bytes(content)
        original.chmod(0o444)  # lecture seule : l'original n'est jamais réécrit
        meta = {
            "id": workbook_id, "filename": Path(filename).name, "suffix": suffix, "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(), "uploaded_by": user,
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        }
        (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def meta(self, workbook_id: str) -> dict[str, Any]:
        folder = self.workbook_dir(workbook_id)
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        meta["versions"] = self.versions(workbook_id)
        return meta

    @staticmethod
    def original_path(folder: Path) -> Path:
        return next(folder.glob("original.*"))

    def list_workbooks(self) -> list[dict[str, Any]]:
        items = []
        for folder in self.workbooks.iterdir():
            meta_file = folder / "meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                meta["version_count"] = len(list((folder / "versions").glob("*.xls*")))
                items.append(meta)
        return sorted(items, key=lambda m: m["uploaded_at"], reverse=True)

    def versions(self, workbook_id: str) -> list[dict[str, Any]]:
        folder = self.workbook_dir(workbook_id) / "versions"
        items = []
        for path in sorted(folder.glob("*.xls*"), key=lambda p: p.stat().st_mtime, reverse=True):
            info_file = path.with_suffix(".json")
            info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else {}
            items.append({"name": path.name, "size": path.stat().st_size,
                          "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"), **info})
        return items

    def next_version_path(self, folder: Path, filename: str) -> tuple[Path, int]:
        versions = folder / "versions"
        versions.mkdir(exist_ok=True)
        number = len(list(versions.glob("*.xls*"))) + 1
        stem, suffix = Path(filename).stem, Path(filename).suffix or ".xlsx"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_stem = re.sub(r"[^\w\-]+", "_", stem).strip("_") or "classeur"
        return versions / f"{safe_stem}_v{number}_{stamp}{suffix}", number

    def delete_workbook(self, workbook_id: str) -> None:
        folder = self.workbook_dir(workbook_id)
        for path in folder.rglob("*"):
            path.chmod(0o644) if path.is_file() else None
        shutil.rmtree(folder)

    # ---------------------------------------------------------------- recettes
    def _recipe_path(self, recipe_id: str) -> Path:
        if not re.fullmatch(r"rc_[a-f0-9]{12}", recipe_id):
            raise FileNotFoundError(recipe_id)
        return self.recipes / f"{recipe_id}.yaml"

    def save_recipe(self, recipe: dict[str, Any], user: str) -> dict[str, Any]:
        recipe = dict(recipe)
        recipe.setdefault("id", f"rc_{uuid.uuid4().hex[:12]}")
        now = datetime.now().isoformat(timespec="seconds")
        path = self._recipe_path(recipe["id"])
        if path.exists():
            previous = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            recipe["created_at"] = previous.get("created_at", now)
            recipe["created_by"] = previous.get("created_by", user)
        else:
            recipe["created_at"], recipe["created_by"] = now, user
        recipe["updated_at"] = now
        path.write_text(yaml.safe_dump(recipe, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return recipe

    def get_recipe(self, recipe_id: str) -> dict[str, Any]:
        path = self._recipe_path(recipe_id)
        if not path.exists():
            raise FileNotFoundError(recipe_id)
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def list_recipes(self) -> list[dict[str, Any]]:
        items = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in self.recipes.glob("rc_*.yaml")]
        return sorted(items, key=lambda r: r.get("updated_at", ""), reverse=True)

    def delete_recipe(self, recipe_id: str) -> None:
        self._recipe_path(recipe_id).unlink(missing_ok=True)
