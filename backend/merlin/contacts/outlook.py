"""Lecture d'Outlook (classique, Windows) : tous les dossiers de toutes les boîtes ouvertes, seulement les mails où
l'adresse de l'équipe RFP est en destinataire ou en copie. Filtre côté Outlook (DASL), donc rapide même sur de grosses
boîtes. Lecture seule : rien n'est jamais déplacé, marqué ou modifié.

Ne garde que ce qui sert à l'inventaire : objet, date, expéditeur, destinataires (nom, adresse, service de l'annuaire),
questions extraites, noms des pièces jointes Excel lues. Les corps de mail ne sont jamais enregistrés.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from .extract import excel_questions, frame, questions

PR_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


class OutlookUnavailable(Exception):
    pass


def available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


class OutlookReader:
    def __init__(self):
        if not available():
            raise OutlookUnavailable("Outlook n'est lisible que sur le poste Windows, avec Outlook classique et pywin32.")
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        try:
            self.ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        except Exception as error:  # noqa: BLE001
            raise OutlookUnavailable("Outlook ne répond pas : ouvrez Outlook classique (le « nouvel Outlook » n'est pas lisible "
                                     "par les applications), puis relancez.") from error
        self._people: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------ personnes (annuaire)
    def person(self, entry: Any, fallback_name: str = "", fallback_email: str = "") -> dict[str, str]:
        key = (fallback_email or fallback_name).lower()
        if key and key in self._people:
            return self._people[key]
        name, email, dept, title, is_list = fallback_name, fallback_email, "", "", False
        try:
            user = entry.GetExchangeUser() if entry is not None else None
            if user is not None:
                name, email = user.Name or name, user.PrimarySmtpAddress or email
                dept, title = user.Department or "", user.JobTitle or ""
            elif entry is not None and entry.GetExchangeDistributionList() is not None:
                dl = entry.GetExchangeDistributionList()
                name, email, is_list = dl.Name or name, dl.PrimarySmtpAddress or email, True
        except Exception:  # noqa: BLE001 - destinataire externe ou annuaire hors ligne
            pass
        if not email and entry is not None:
            try:
                email = entry.PropertyAccessor.GetProperty(PR_SMTP)
            except Exception:  # noqa: BLE001
                pass
        p = {"name": name, "email": (email or "").lower(), "department": dept, "title": title, "list": is_list}
        if key:
            self._people[key] = p
        return p

    def members(self, token: str) -> set[str]:
        """Membres de la liste de diffusion de l'équipe RFP (adresses) : leurs mails sont des demandes, et ils ne sont
        jamais « la personne à contacter »."""
        try:
            entry = self.ns.CreateRecipient(token)
            entry.Resolve()
            dl = entry.AddressEntry.GetExchangeDistributionList()
            out = set()
            for m in dl.GetExchangeDistributionListMembers():
                u = m.GetExchangeUser()
                if u is not None and u.PrimarySmtpAddress:
                    out.add(u.PrimarySmtpAddress.lower())
            return out
        except Exception:  # noqa: BLE001
            return set()

    # ------------------------------------------------------------------ dossiers
    def _folders(self, root) -> Iterator[Any]:
        stack = [root]
        while stack:
            f = stack.pop()
            yield f
            try:
                stack.extend(list(f.Folders))
            except Exception:  # noqa: BLE001
                continue

    def scan(self, token: str, since: datetime, progress: Callable[[str, int], None], stop: Callable[[], bool]) -> Iterator[dict[str, Any]]:
        t = token.replace("'", "''")
        when = since.strftime("%Y-%m-%d %H:%M")
        dasl = ("@SQL=(\"urn:schemas:httpmail:displayto\" LIKE '%{t}%' OR \"urn:schemas:httpmail:displaycc\" LIKE '%{t}%') "
                "AND \"urn:schemas:httpmail:datereceived\" >= '{w}'").format(t=t, w=when)
        seen: set[str] = set()
        tmp = Path(tempfile.mkdtemp(prefix="merlin-mails-"))
        for store in list(self.ns.Stores):
            try:
                root = store.GetRootFolder()
            except Exception:  # noqa: BLE001
                continue
            for folder in self._folders(root):
                if stop():
                    return
                try:
                    if folder.DefaultItemType != 0:  # 0 = courrier (pas calendrier, contacts…)
                        continue
                    items = folder.Items.Restrict(dasl)
                except Exception:  # noqa: BLE001
                    continue
                progress(folder.FolderPath, 0)
                for item in items:
                    if stop():
                        return
                    try:
                        if item.Class != 43:  # 43 = MailItem
                            continue
                        mid = item.EntryID
                        if mid in seen:
                            continue
                        seen.add(mid)
                        yield self._mail(item, tmp)
                        progress(folder.FolderPath, 1)
                    except Exception:  # noqa: BLE001 - un mail illisible n'arrête pas les autres
                        continue

    def _mail(self, item: Any, tmp: Path) -> dict[str, Any]:
        sender = self.person(getattr(item, "Sender", None), item.SenderName or "", item.SenderEmailAddress or "")
        to, cc = [], []
        for r in item.Recipients:
            p = self.person(r.AddressEntry, r.Name or "", r.Address or "")
            (to if r.Type == 1 else cc if r.Type == 2 else []).append(p)
        qs = questions(item.Body or "")
        files = []
        for att in item.Attachments:
            name = att.FileName or ""
            if name.lower().endswith((".xlsx", ".xlsm")):
                target = tmp / name
                try:
                    att.SaveAsFile(str(target))
                    found = excel_questions(target)
                    if found:
                        qs += found
                        files.append(name)
                finally:
                    target.unlink(missing_ok=True)
        sent = item.SentOn
        return {"id": item.EntryID, "conversation": getattr(item, "ConversationID", "") or "", "subject": item.Subject or "",
                "date": datetime(sent.year, sent.month, sent.day).date().isoformat() if sent else "",
                "sender": sender, "to": to, "cc": cc, "questions": qs, "attachments": files, "frame": frame(item.Body or "")}


def since_months(months: int) -> datetime:
    return datetime.now() - timedelta(days=int(months * 30.5))


__all__ = ["OutlookReader", "OutlookUnavailable", "available", "since_months"]
