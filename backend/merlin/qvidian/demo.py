"""Bibliothèque Qvidian de démonstration : contenus fictifs (fonds imaginaires, ISIN QZ…), même interface que le client.

Elle contient exprès des défauts pour la carte des erreurs (code dans les textes, textes dépassés, doublons, contenus
expirés ou jamais utilisés) et plusieurs versions d'une même réponse pour montrer l'agrégation récence × fréquence.
Jamais mélangée aux vraies données : instantané séparé, et utilisée dans les RFI seulement en mode démonstration.
"""
from __future__ import annotations

import copy
import io
from datetime import date
from typing import Any

from .client import Binding, normalize_content

FOLDERS = [
    (1, 0, "Bibliothèque"),
    (10, 1, "Société"), (11, 10, "Présentation"), (12, 10, "Gouvernance"),
    (20, 1, "Gestion"), (21, 20, "Processus d'investissement"), (22, 20, "Risques"),
    (30, 1, "ESG"), (31, 30, "Politique ESG"), (32, 30, "Vote et engagement"),
    (40, 1, "Opérations"), (41, 40, "Valorisation"), (42, 40, "Dépositaire"),
    (50, 1, "Fonds"), (51, 50, "Fonds Imaginaire Horizon"), (52, 50, "Fonds Imaginaire Aurore"),
]

# (id, dossier, question, texte, révision, utilisations, dernière utilisation, modifié, créé, extras)
_C = [
    (1001, 11, "Présentez votre société de gestion.",
     "Société de Gestion Imaginaire est une société de gestion indépendante fondée en 1998, agréée par l'AMF. "
     "Elle gère des fonds ouverts et des mandats pour une clientèle institutionnelle et privée.", 4, 52, "2026-09-12", "2026-02-03", "2015-04-01", {}),
    (1002, 11, "Présentez votre société de gestion.",
     "Société de Gestion Imaginaire est une société de gestion indépendante créée en 1998 et agréée par l'AMF. Elle gère "
     "des fonds ouverts et des mandats pour des clients institutionnels et privés.", 2, 31, "2024-05-20", "2022-06-10", "2015-04-01", {}),
    (1003, 11, "Quel est l'encours sous gestion de la société ?",
     "Au 31/12/2019, l'encours sous gestion s'élève à 12 milliards d'euros.", 1, 40, "2021-03-02", "2020-01-15", "2018-01-10", {}),
    (1004, 12, "Décrivez la gouvernance de la société.",
     "La société est dirigée par un directoire de trois membres, contrôlé par un conseil de surveillance. "
     "Un comité des risques se réunit chaque mois.", 3, 18, "2026-07-01", "2025-11-20", "2016-02-01", {}),
    (1005, 12, "Décrivez la gouvernance de la société.",
     "La société est dirigée par un directoire de trois membres, contrôlé par un conseil de surveillance. Un comité des "
     "risques se réunit chaque mois.&lt;br&gt;&lt;br&gt;{{NOM_DIRIGEANT}}", 1, 2, "2019-03-01", "2018-09-01", "2016-02-01", {}),
    (1006, 21, "Décrivez votre processus d'investissement.",
     "Notre processus d'investissement combine une analyse fondamentale des émetteurs, une construction de portefeuille "
     "disciplinée et un contrôle des risques indépendant de la gestion.", 5, 77, "2026-10-01", "2026-05-14", "2014-01-01", {}),
    (1007, 21, "Décrivez votre processus d'investissement.",
     "Notre processus combine analyse fondamentale, construction de portefeuille et contrôle des risques. "
     "Voir annexe. mso-bidi-font-size:11pt;font-family:\"Arial\"", 2, 9, "2020-11-05", "2019-07-01", "2014-01-01", {}),
    (1008, 22, "Comment les risques sont-ils suivis ?",
     "Les risques sont suivis quotidiennement par une équipe indépendante. Les limites sont paramétrées dans l'outil "
     "de contrôle et toute alerte est escaladée au comité des risques.", 2, 26, "2026-08-19", "2025-03-03", "2017-05-05", {}),
    (1009, 22, "Utilisez-vous des dérivés ?",
     "TBD", 1, 0, None, "2021-02-02", "2021-02-02", {}),
    (1010, 31, "Décrivez votre politique ESG.",
     "Notre politique ESG intègre des critères environnementaux, sociaux et de gouvernance à chaque étape de l'analyse. "
     "Les fonds concernés sont classés article 8 au sens du règlement SFDR.", 6, 64, "2026-09-30", "2026-03-01", "2018-03-01", {}),
    (1011, 31, "Décrivez votre politique ESG.",
     "Notre politique ESG intègre des critères environnementaux, sociaux et de gouvernance. Les informations figurent "
     "dans le DICI et le prospectus des fonds.", 3, 20, "2022-01-10", "2020-06-01", "2018-03-01", {}),
    (1012, 32, "Quelle est votre politique de vote ?",
     "Nous exerçons les droits de vote pour l'ensemble des fonds, selon une politique publiée chaque année, avec un "
     "rapport annuel d'exercice des votes.", 4, 30, "2023-04-11", "2021-04-01", "2016-01-01", {}),
    (1013, 32, "Quelle est votre politique de vote ?",
     "Nous votons à toutes les assemblées générales des sociétés détenues en portefeuille, selon une politique de vote "
     "publiée et revue chaque année. Un rapport annuel détaille les votes exercés.", 2, 8, "2026-09-25", "2026-01-15", "2025-12-01", {}),
    (1014, 41, "Quelle est la fréquence de valorisation ?",
     "La valeur liquidative est calculée chaque jour ouvré.", 1, 45, "2026-06-30", "2023-05-05", "2015-01-01", {}),
    (1015, 41, "Quel taux de référence utilisez-vous pour la trésorerie ?",
     "La trésorerie est rémunérée sur la base de l'EONIA capitalisé.", 1, 12, "2020-12-15", "2019-01-01", "2016-01-01", {"Expired": "true"}),
    (1016, 42, "Qui est le dépositaire ?",
     "Le dépositaire des fonds est Banque Dépositaire Imaginaire.", 1, 38, "2026-04-04", "2024-02-01", "2015-01-01",
     {"DateToExpire": "2026-01-31T00:00:00"}),
    (1017, 42, "Who is the depositary of the funds?",
     "Le dépositaire des fonds est Banque Dépositaire Imaginaire, qui assure la garde des actifs et le contrôle de la "
     "régularité des décisions de la société de gestion pour le compte des porteurs.", 1, 3, "2025-02-02", "2024-02-01", "2023-01-01", {"LCID": "1033", "LCIDLanguage": "English"}),
    (1018, 51, "Quel est l'objectif de gestion du Fonds Imaginaire Horizon ?",
     "Le Fonds Imaginaire Horizon (part C, ISIN QZ0000000011) vise une performance supérieure à son indicateur de référence "
     "sur une durée de placement recommandée de 5 ans.", 2, 14, "2026-05-05", "2025-09-09", "2020-01-01", {}),
    (1019, 52, "Quel est l'objectif de gestion du Fonds Imaginaire Aurore ?",
     "Le Fonds Imaginaire Aurore (ISIN QZ0000000029) vise #REF! sur une durée de placement recommandée de [object Object] ans.",
     1, 0, None, "2021-08-08", "2021-08-08", {}),
    (1020, 52, "Le fonds est-il éligible au PEA ?",
     "Oui, le Fonds Imaginaire Aurore est éligible au PEA.", 1, 0, None, "2020-03-03", "2020-03-03", {}),
]

PROJECTS = [
    {"ProjectID": "501", "ProjectName": "Appel d'offres Caisse Imaginaire 2025", "DocTypeName": "RFP", "DateCreated": "2025-03-10T09:00:00",
     "StatusString": "Gagné", "Archived": "false"},
    {"ProjectID": "502", "ProjectName": "Questionnaire Mutuelle Imaginaire 2026", "DocTypeName": "RFP", "DateCreated": "2026-06-02T09:00:00",
     "StatusString": "En cours", "Archived": "false"},
]
PROJECT_ANSWERS = {
    501: [("Présentez votre société de gestion.", 1002), ("Quelle est votre politique de vote ?", 1012),
          ("Décrivez votre processus d'investissement.", 1006)],
    502: [("Présentez votre société de gestion.", 1001), ("Quelle est votre politique de vote ?", 1013),
          ("Décrivez votre politique ESG.", 1010)],
}


def _content(row) -> dict[str, Any]:
    cid, folder, question, text, rev, uses, last_used, modified, created, extra = row
    path = _path(folder)
    c = {"ContentID": str(cid), "Revision": str(rev), "GUID": f"demo-{cid}", "LibraryFolderID": str(folder),
         "LibraryFolderTitle": path.split(" / ")[-1], "LibraryFolderPath": path, "ContentText": text, "Enabled": "true",
         "ContentType": "QA", "ContentTypeName": "Q&A", "LCID": "1036", "LCIDLanguage": "Français", "Expired": "false",
         "DateCreated": f"{created}T09:00:00", "DateLastModified": f"{modified}T09:00:00",
         "DateLastUsed": f"{last_used}T09:00:00" if last_used else None, "DateToExpire": None, "TimesUsedCount": str(uses),
         "Title": question, "CurrentOwnersName": "Équipe RFP (démo)", "LastModifiedByUserName": "Utilisateur démo",
         "AlertText": "", "AlertActive": "false", "InlineEdit": "true", "CheckedOut": "false", "EditPerm": "true",
         "SubmittedContentMetadata": {"QuestionText": question}, "Comments": ""}
    c.update(extra)
    return c


def _path(folder_id: int) -> str:
    by_id = {f[0]: f for f in FOLDERS}
    parts = []
    while folder_id and folder_id in by_id:
        fid, parent, title = by_id[folder_id]
        if parent:
            parts.append(title)
        folder_id = parent
    return " / ".join(reversed(parts))


class DemoQvidian:
    """Même interface que QvidianClient ; les écritures modifient la copie en mémoire (jamais un vrai Qvidian)."""
    mode = "demo"
    extended_fields = True

    def __init__(self):
        self.contents = {int(r[0]): _content(r) for r in _C}
        self.binding = Binding("demo-token", "demo", "demo://qvidian", {})
        self.writes: list[tuple[list[int], dict]] = []

    connected = True

    def connect(self, user: str, password: str) -> Binding:
        return self.binding

    connect_api_key = connect

    def connect_token(self, user: str, token: str) -> Binding:
        return self.binding

    def terminate(self) -> None:
        return None

    def has_permission(self, permission: str) -> bool:
        return True

    def top_folder(self) -> dict[str, Any]:
        return {"id": 1, "parent_id": 0, "title": "Bibliothèque", "children": 5, "contents": 0, "enabled": True}

    def folders(self, parent_id: int) -> list[dict[str, Any]]:
        out = []
        for fid, parent, title in FOLDERS:
            if parent == parent_id:
                out.append({"id": fid, "parent_id": parent, "title": title, "children": sum(1 for f in FOLDERS if f[1] == fid),
                            "contents": sum(1 for c in self.contents.values() if int(c["LibraryFolderID"]) == fid), "enabled": True})
        return out

    def folder_contents(self, folder_id: int) -> list[dict[str, Any]]:
        return [normalize_content(copy.deepcopy(c)) for c in self.contents.values() if int(c["LibraryFolderID"]) == folder_id]

    def content(self, content_id: int) -> dict[str, Any]:
        return normalize_content(copy.deepcopy(self.contents[content_id]))

    def preview_html(self, content_id: int, revision: int) -> str:
        return f"<p>{self.contents[content_id]['ContentText']}</p>"

    def search(self, terms: str = "", page: int = 0, size: int = 50, **_: Any) -> tuple[int, list[dict[str, Any]]]:
        words = [w for w in terms.lower().split() if len(w) > 2]
        hits = [c for c in self.contents.values() if not words or any(w in (c["Title"] + " " + c["ContentText"]).lower() for w in words)]
        return len(hits), [normalize_content(copy.deepcopy(c)) for c in hits[page * size:(page + 1) * size]]

    def projects(self, mode: str = "AllProjects", page: int = 1, size: int = 50) -> tuple[int, list[dict[str, Any]]]:
        rows = [{"id": int(p["ProjectID"]), "name": p["ProjectName"], "type": p["DocTypeName"], "created": p["DateCreated"][:10],
                 "last_used": None, "proposal_date": None, "status": p["StatusString"], "archived": False, "owners": ""} for p in PROJECTS]
        return len(rows), rows[(page - 1) * size: page * size]

    def project_documents(self, project_id: int) -> list[dict[str, Any]]:
        p = next(p for p in PROJECTS if int(p["ProjectID"]) == project_id)
        return [{"id": 1, "project_id": project_id, "name": f"{p['ProjectName']} - réponse finale", "ext": "xlsx", "created": p["DateCreated"][:10], "by": "démo"}]

    def project_document(self, project_id: int, document_id: int) -> tuple[str, bytes]:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Questionnaire"
        ws.append(["Question", "Réponse"])
        for question, cid in PROJECT_ANSWERS[project_id]:
            ws.append([question, self.contents[cid]["ContentText"]])
        ws.column_dimensions["A"].width = 60
        ws.column_dimensions["B"].width = 100
        buf = io.BytesIO()
        wb.save(buf)
        return f"Projet_{project_id}_reponse_finale.xlsx", buf.getvalue()

    def audit_events(self, event_ids=None, page: int = 0, size: int = 100):
        return 0, []

    def update_details(self, content_ids: list[int], changes: dict[str, Any]) -> list[dict[str, Any]]:
        self.writes.append((list(content_ids), dict(changes)))
        for cid in content_ids:
            c = self.contents.get(cid)
            if c is None:
                continue
            for key, value in changes.items():
                if key == "ContentText":
                    c["ContentText"] = value
                    c["Revision"] = str(int(c["Revision"]) + 1)
                elif key == "Enabled":
                    c["Enabled"] = "true" if value else "false"
                elif key == "AlertEnabled":
                    c["AlertActive"] = "true" if value else "false"
                elif key == "DateToExpire":
                    c["DateToExpire"] = f"{value}T00:00:00" if value else None
                else:
                    c[key] = value
            c["DateLastModified"] = f"{date.today().isoformat()}T09:00:00"
        return []


__all__ = ["DemoQvidian", "FOLDERS", "PROJECTS"]
