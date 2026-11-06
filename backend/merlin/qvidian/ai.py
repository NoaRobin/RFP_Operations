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
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .client import is_excerpt

BATCH_CHARS = 9000
KINDS = {"code": "code informatique", "depasse": "dépassé", "incoherent": "incohérent", "forme": "forme", "orthographe": "orthographe", "erreur": "erreur"}
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
    text = (c.get("text") or "").strip()  # texte entier : les lots sont déjà découpés par taille
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


# ---------------------------------------------------------------------------------------------- export JSON → chat → Excel
PART_CHARS = 160_000  # texte par fichier : tient dans la fenêtre d'un chat récent, avec le prompt et la réponse
SHEETS = {  # onglet de l'Excel de retour → catégorie de la carte des erreurs
    "Textes dépassés": "depasse", "Orthographe": "orthographe", "Incohérences": "incoherent",
    "Erreurs": "erreur", "Code et mise en forme": "code", "Forme et ton": "forme",
}
COLUMNS = ["ID", "Titre", "Extrait concerné", "Problème", "Correction proposée", "Gravité"]

JSON_PROMPT = """Tu es relecteur expert de la bibliothèque de réponses types (Qvidian) d'une équipe RFP d'une société de gestion
d'actifs. Le champ « textes » contient les textes à relire (id, titre, question type, texte, dossier, langue, dates).
Date du jour : {today}. Partie {part} sur {parts}.

Relis CHAQUE texte et signale uniquement de vrais problèmes, en citant l'extrait exact :
1. Textes dépassés : date ou chiffre ancien (encours, effectifs, performances « au 31/12/2021 »…), réglementation
   remplacée ou mal nommée (ex. SFDR, PRIIPs, MiFID), nom de personne, d'entité, de fonds ou de document qui n'existe plus.
2. Orthographe : fautes d'orthographe, de grammaire, d'accord, de typographie (espaces, majuscules), en français comme en anglais.
3. Incohérences : contradiction dans le texte ou avec un autre texte de la liste (chiffre, date, nom différents), phrase
   coupée, texte qui ne répond pas à sa question type, mélange de fonds.
4. Erreurs : affirmation probablement fausse, chiffre invraisemblable, référence cassée, information manquante essentielle.
5. Code et mise en forme : code informatique, balises, variables {{{{…}}}}, erreurs Excel (#N/A, #REF!), mise en forme collée.
6. Forme et ton : langues mélangées, ton non professionnel, répétitions, phrase trop longue ou ambiguë.

Règles : n'invente rien ; si « texte_complet » vaut false, Qvidian n'a donné qu'un extrait : ne signale pas la fin coupée ; si tu n'es pas sûr, ne signale pas ; un texte sans problème n'apparaît nulle part.
Propose une correction concrète (le texte corrigé quand c'est possible).

Réponds par un FICHIER EXCEL (.xlsx) à télécharger, avec exactement ces onglets :
{sheets}
Dans chaque onglet, une ligne par problème, avec exactement ces colonnes dans cet ordre :
{columns}
« ID » = l'id du texte (nombre). « Gravité » = haute, moyenne ou basse. Ajoute un onglet « Synthèse » avec le nombre de
problèmes par onglet et les 10 textes les plus urgents. Si un onglet n'a aucun problème, laisse seulement les en-têtes.
"""


def _entry(c: dict[str, Any]) -> dict[str, Any]:
    return {"id": c["id"], "titre": c.get("title") or "", "question_type": c.get("question") or "", "texte": c.get("text") or "",
            "dossier": c.get("folder_path") or "", "langue": c.get("language") or "", "modifie_le": (c.get("modified") or "")[:10],
            "expire_le": (c.get("expires") or "")[:10], "utilisations": c.get("times_used") or 0, "derniere_utilisation": (c.get("last_used") or "")[:10],
            "texte_complet": not is_excerpt(c)}


def json_pack(contents: list[dict[str, Any]], today: str | None = None) -> list[dict[str, Any]]:
    """Fichiers JSON prêts à déposer dans un chat : prompt + format de retour + textes ; plusieurs parties si besoin."""
    today = today or date.today().isoformat()
    parts: list[list[dict[str, Any]]] = [[]]
    size = 0
    for c in contents:
        e = _entry(c)
        n = len(e["texte"]) + len(e["titre"]) + 200
        if parts[-1] and size + n > PART_CHARS:
            parts.append([])
            size = 0
        parts[-1].append(e)
        size += n
    out = []
    for k, texts in enumerate(parts, 1):
        prompt = JSON_PROMPT.format(today=today, part=k, parts=len(parts), sheets="\n".join(f"- {s}" for s in SHEETS),
                                    columns=" | ".join(COLUMNS))
        out.append({"consignes": prompt, "format_de_retour": {"fichier": "Excel (.xlsx)", "onglets": list(SHEETS) + ["Synthèse"], "colonnes": COLUMNS},
                    "date_du_jour": today, "partie": f"{k}/{len(parts)}", "nombre_de_textes": len(texts), "textes": texts})
    return out


def _norm(s: str) -> str:
    s = "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z]+", " ", s.lower()).strip()


def parse_xlsx(content: bytes, known: set[int]) -> dict[str, Any]:
    """Excel rendu par le chat : un onglet par catégorie, colonnes ID | Titre | Extrait | Problème | Correction | Gravité.
    Tolérant (ordre des colonnes, « C123 » ou « 123 », noms d'onglets approchants) ; les ID inconnus sont signalés."""
    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet_kind = {_norm(k): v for k, v in SHEETS.items()}
    findings: dict[int, list[dict[str, str]]] = {}
    unknown, read, sheets = set(), 0, {}
    for ws in wb.worksheets:
        name = _norm(ws.title)
        kind = sheet_kind.get(name) or next((v for k, v in sheet_kind.items() if k.split()[0] in name), None)
        if kind is None:
            continue  # « Synthèse » et autres onglets : ignorés
        rows = ws.iter_rows(values_only=True)
        head = None
        for r in rows:
            cells = [_norm(c) for c in r]
            if "id" in cells:
                head = cells
                break
        if head is None:
            continue
        col = lambda *names: next((i for i, h in enumerate(head) if any(h.startswith(n) for n in names)), None)  # noqa: E731
        ci, cx, cp, cf, cg = col("id"), col("extrait"), col("probleme"), col("correction"), col("gravite")
        n = 0
        for r in rows:
            if not r or ci is None or r[ci] in (None, ""):
                continue
            m = re.search(r"\d+", str(r[ci]))
            if not m:
                continue
            cid = int(m.group())
            if cid not in known:
                unknown.add(cid)
                continue
            problem = str(r[cp] or "").strip() if cp is not None else ""
            if not problem:
                continue
            excerpt = str(r[cx] or "").strip() if cx is not None else ""
            sev = _norm(r[cg]) if cg is not None else ""
            findings.setdefault(cid, []).append({"kind": KINDS[kind], "severity": SEVERITIES.get(sev, "moyenne"),
                                                 "problem": (problem + (f" — « {excerpt[:200]} »" if excerpt else ""))[:600],
                                                 "fix": str(r[cf] or "").strip()[:800] if cf is not None else ""})
            n += 1
        sheets[ws.title] = n
        read += n
    return {"findings": findings, "read": read, "unknown": sorted(unknown), "sheets": sheets}


__all__ = ["build_prompts", "parse_reply", "FindingStore", "KINDS", "json_pack", "parse_xlsx", "SHEETS", "COLUMNS"]
