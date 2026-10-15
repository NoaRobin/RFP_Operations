"""Analyse IA des contenus Qvidian, sans API : prompt à coller dans Copilot (Microsoft 365), réponse collée relue ici.

Même principe que l'aller-retour Copilot du compléteur RFI (`merlin/rfi/copilot.py`) : identifiants C<id>, format de
retour imposé (tableau), lots de la taille d'un message, et la réponse est contrôlée avant d'être gardée. Les constats
sont rangés dans data/qvidian/ai_findings.json (jamais committé) et apparaissent dans la carte des erreurs (colonne
« Analyse IA »). Un constat est lié à la révision du contenu : il disparaît quand le contenu est modifié.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

BATCH_CHARS = 9000
KINDS = {"code": "code informatique", "depasse": "dépassé", "incoherent": "incohérent", "forme": "forme"}
SEVERITIES = {"haute": "haute", "high": "haute", "moyenne": "moyenne", "medium": "moyenne", "basse": "basse", "low": "basse"}
PROMPT_HEAD = """Tu relis des réponses types de la bibliothèque Qvidian d'une équipe RFP (société de gestion d'actifs).
Pour chaque contenu « C… » ci-dessous, signale seulement de vrais problèmes :
- code : code informatique, balises, variables {{{{…}}}}, erreurs Excel, mise en forme collée dans le texte ;
- depasse : information dépassée (date ou chiffre ancien, réglementation remplacée, nom ou document qui n'existe plus) ;
- incoherent : contradiction, phrase coupée, texte qui ne répond pas à la question ;
- forme : faute, langues mélangées, ton non professionnel.
N'invente rien. Si tu n'es pas sûr, n'écris pas de ligne. Un contenu sans problème n'a pas de ligne.
Réponds UNIQUEMENT avec ce tableau, une ligne par problème :
| ID | Catégorie | Gravité | Problème | Correction proposée |
|---|---|---|---|---|
| C123 | depasse | moyenne | L'encours cité date de 2019. | Mettre à jour l'encours à la dernière date connue. |
Catégorie : code, depasse, incoherent ou forme. Gravité : haute, moyenne ou basse.
Date du jour : {today}.

Contenus :
"""
ROW = re.compile(r"^\s*\|?\s*\**\s*C\s*(\d+)\s*\**\s*\|(.*)$", re.I)


def _block(c: dict[str, Any]) -> str:
    text = (c.get("text") or "").strip()
    if len(text) > 1500:
        text = text[:1500] + " […]"
    return (f"C{c['id']} — Question : {c.get('title') or '—'}\nDossier : {c.get('folder_path') or '—'} · dernière modification : "
            f"{c.get('modified') or '—'}\nTexte :\n{text or '(vide)'}\n")


def build_prompts(contents: list[dict[str, Any]], today: str | None = None) -> dict[str, Any]:
    today = today or datetime.now().strftime("%d/%m/%Y")
    head = PROMPT_HEAD.format(today=today)
    batches, current, ids = [], [], []
    for c in contents:
        block = _block(c)
        if current and len(head) + sum(len(b) for b in current) + len(block) > BATCH_CHARS:
            batches.append((current, ids))
            current, ids = [], []
        current.append(block)
        ids.append(c["id"])
    if current:
        batches.append((current, ids))
    return {"batches": [{"prompt": head + "\n".join(blocks), "ids": batch_ids, "chars": len(head) + sum(len(b) for b in blocks)}
                        for blocks, batch_ids in batches], "count": len(contents)}


def parse_reply(text: str, ids: list[int]) -> dict[str, Any]:
    allowed = set(ids)
    findings: dict[int, list[dict[str, str]]] = {i: [] for i in ids}
    unknown, read = set(), 0
    for line in (text or "").splitlines():
        m = ROW.match(line.replace(" ", " "))
        if not m:
            continue
        cid = int(m.group(1))
        cells = [x.strip().strip("*`").strip() for x in m.group(2).rstrip().rstrip("|").split("|")]
        cells += [""] * (4 - len(cells))
        kind, severity, problem, fix = cells[0].lower(), cells[1].lower(), cells[2], cells[3]
        if cid not in allowed:
            unknown.add(f"C{cid}")
            continue
        if not problem:
            continue
        read += 1
        plain = unicodedata.normalize("NFKD", kind)
        plain = "".join(ch for ch in plain if not unicodedata.combining(ch))  # « dépassé » → « depasse »
        kind = next((k for k in KINDS if plain.startswith(k[:4])), "forme")
        severity = "".join(ch for ch in unicodedata.normalize("NFKD", severity) if not unicodedata.combining(ch))
        findings[cid].append({"kind": KINDS[kind], "severity": SEVERITIES.get(severity, "moyenne"), "problem": problem[:500], "fix": fix[:500]})
    return {"findings": findings, "read": read, "unknown": sorted(unknown)}


class FindingStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self, findings: dict[int, list[dict[str, str]]], revisions: dict[int, int]) -> int:
        data = self.load()
        now = datetime.now().isoformat(timespec="seconds")
        for cid, items in findings.items():
            data[str(cid)] = {"revision": revisions.get(cid), "at": now, "findings": items}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
        return sum(len(v) for v in findings.values())


__all__ = ["build_prompts", "parse_reply", "FindingStore", "KINDS"]
