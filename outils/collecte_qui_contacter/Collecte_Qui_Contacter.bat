@echo off
REM Collecte "Qui contacter" : double-cliquer. Installe ce qu'il faut la premiere fois (Python et 2 bibliotheques,
REM dans le profil de l'utilisateur, sans droits administrateur), puis lit Outlook et construit le glossaire.
REM Un seul fichier a copier dans le dossier SharePoint "Glossaire .PY". Resultat : "Glossaire qui contacter.xlsx"
REM (questions, equipe, personnes, types de DD, mails types) + dossier Collectes (une collecte par personne).
REM Lu : mails avec AmeuRFPteam en copie (36 mois). Jamais garde : corps des mails, reponses, pieces jointes.
REM Les corrections faites dans les colonnes "(corrigee)" du glossaire sont conservees a chaque lancement.
setlocal EnableExtensions
chcp 65001 >nul
title Collecte Qui contacter - equipe RFP
cd /d "%~dp0"
REM Dossier hors de AppData : le Python du Microsoft Store redirige AppData\Local vers son propre dossier
set "BASE=%USERPROFILE%\.rfpcollecte"
set "VENV=%BASE%\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "PYVER=3.12.10"

if exist "%VPY%" goto deps

echo.
echo   Premiere utilisation : installation (quelques minutes, une seule fois).
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY if exist "%BASE%\Python312\python.exe" set PY="%BASE%\Python312\python.exe"
if defined PY goto venv

echo   Python n'est pas installe : telechargement depuis python.org (version %PYVER%, pour vous seul)...
if not exist "%BASE%" mkdir "%BASE%"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; [Net.WebRequest]::DefaultWebProxy.Credentials=[Net.CredentialCache]::DefaultNetworkCredentials; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%BASE%\python-installer.exe'"
if errorlevel 1 goto nopython
"%BASE%\python-installer.exe" /quiet InstallAllUsers=0 Include_launcher=0 PrependPath=0 Include_test=0 Shortcuts=0 TargetDir="%BASE%\Python312"
if not exist "%BASE%\Python312\python.exe" goto nopython
del "%BASE%\python-installer.exe" >nul 2>nul
set PY="%BASE%\Python312\python.exe"

:venv
echo   Preparation de l'environnement...
%PY% -m venv "%VENV%"
if exist "%VPY%" goto deps
REM Python du Microsoft Store : l'environnement a pu etre cree dans son dossier redirige
for /d %%D in ("%LOCALAPPDATA%\Packages\PythonSoftwareFoundation.Python.*") do (
  if exist "%%D\LocalCache\Local\RFPCollecte\venv\Scripts\python.exe" set "VPY=%%D\LocalCache\Local\RFPCollecte\venv\Scripts\python.exe"
)
if exist "%VPY%" goto deps
REM Dernier recours : le Python trouve directement, bibliotheques installees pour l'utilisateur
set VPY=%PY%
for /f "delims=" %%P in ('%PY% -c "import sys; print(sys.executable)"') do set "VPY=%%P"
if not exist "%VPY%" goto failed
"%VPY%" -c "import win32com.client, openpyxl" >nul 2>nul
if not errorlevel 1 goto run
echo   Installation des bibliotheques (pywin32, openpyxl)...
"%VPY%" -m pip install --user --disable-pip-version-check -q pywin32 openpyxl
if errorlevel 1 goto nopip
goto run

:deps
"%VPY%" -c "import win32com.client, openpyxl" >nul 2>nul
if not errorlevel 1 goto run
echo   Installation des bibliotheques (pywin32, openpyxl)...
"%VPY%" -m pip install --disable-pip-version-check -q pywin32 openpyxl
if errorlevel 1 goto nopip

:run
echo.
REM Le script Python est contenu dans ce .bat (apres la ligne marqueur, en fin de fichier) : un seul fichier a copier
set "SELF=%~f0"
set "COLLECTE_DIR=%~dp0"
set "SCRIPT=%BASE%\collecte.py"
if not exist "%BASE%" mkdir "%BASE%"
"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:SELF,[Text.Encoding]::UTF8); $m='#'+'__PYTHON__'; $i=$t.IndexOf($m); if($i -lt 0){exit 1}; [IO.File]::WriteAllText($env:SCRIPT,$t.Substring($i+$m.Length).TrimStart(),(New-Object Text.UTF8Encoding $false))"
if errorlevel 1 if exist "%~dp0collecte.py" set "SCRIPT=%~dp0collecte.py"
"%VPY%" "%SCRIPT%" %*
echo.
pause
exit /b 0

:nopython
echo.
echo   Impossible d'installer Python automatiquement (python.org bloque par le proxy ?).
echo   Installez "Python 3.12" depuis le Portail d'entreprise / Software Center, puis relancez ce fichier.
pause
exit /b 1

:nopip
echo.
echo   Impossible d'installer les bibliotheques (pypi.org bloque par le proxy ?).
echo   Demandez a l'IT l'acces a pypi.org, ou faites installer pywin32 et openpyxl, puis relancez.
pause
exit /b 1

:failed
echo.
echo   Echec de la preparation de l'environnement Python : envoyez une capture de cette fenetre.
pause
exit /b 1
#__PYTHON__
"""Collecte « Qui contacter » — à lancer par Collecte_Qui_Contacter.bat (double-clic), sur le poste d'un collègue.

Lit son Outlook classique (lecture seule) : mails avec l'équipe RFP en destinataire ou en copie, questions posées et
destinataires. Écrit un fichier Excel dans le dossier SharePoint du glossaire. Ce fichier s'importe ensuite dans
l'app (Qui contacter › Importer une collecte), qui fait le tri, les équipes et les mails types.

Autonome : seulement pywin32 et openpyxl. La partie « extraction » est une copie exacte de
backend/merlin/contacts/extract.py (vérifiée par tests/test_contacts.py : les deux doivent rester identiques).
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# ==================================================================================== COPIE DE extract.py
import re
from pathlib import Path

# Début de l'historique cité (Outlook FR / EN) : tout ce qui suit n'est pas ce mail
QUOTE = re.compile(r"^\s*(?:-{2,}\s*(?:original message|message d'origine)|_{8,}|de\s*:\s.+|from\s*:\s.+|envoy[ée] le\s*:|sent\s*:|"
                   r"le .{5,80}a [ée]crit\s*:|on .{5,80}wrote\s*:)", re.I)
SIGN = re.compile(r"^\s*(?:cordialement|bien (?:à|a) (?:vous|toi)|bonne (?:journée|soirée)|merci (?:d'avance|par avance|beaucoup)?[\s,!.]*$|"
                  r"best regards|kind regards|regards|many thanks|thanks in advance|thank you[\s,!.]*$)", re.I)
GREETING = re.compile(r"^\s*(?:bonjour|hello|hi|dear|chers?|chère|salut|bonsoir)\b.*$", re.I)
ITEM = re.compile(r"^\s*(?:[-•*·▪●o]\s+|\(?\d{1,3}(?:\.\d{1,3})*[.)]\s+|\(?[a-z][.)]\s+|q\d+\s*[:.)-]\s*)", re.I)
CONTEXT = re.compile(r"(questions?|pourriez[- ]vous|pouvez[- ]vous|could you|can you|merci de|please|nous avons besoin|we need|"
                     r"je reviens vers vous|dans le cadre)", re.I)
NOISE = re.compile(r"^(?:https?://|www\.|\+?\d[\d .()-]{7,}$|tel\b|tél\b|mob\b|this e-?mail|ce message|confidential|confidentiel)", re.I)


def new_part(body: str) -> str:
    """Texte propre au mail : jusqu'à l'historique cité (« De : », « -----Original Message----- »…)."""
    out = []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if QUOTE.match(line):
            break
        if line.lstrip().startswith(">"):
            continue
        out.append(line)
    return "\n".join(out)


def _clean(line: str) -> str:
    return " ".join(ITEM.sub("", line, count=1).split()).strip(" -–:;")


def questions(body: str) -> list[str]:
    """Questions posées : phrases interrogatives, et éléments de liste qui suivent une demande (« merci de nous
    indiquer : - l'encours… - la date… »). Les formules de politesse, signatures et liens sont ignorés."""
    lines = new_part(body).split("\n")
    out: list[str] = []
    in_list = False
    for raw in lines:
        if SIGN.match(raw):
            break  # signature : la suite n'est jamais une question
        line = raw.strip()
        if not line or GREETING.match(line) or NOISE.match(line):
            in_list = in_list and bool(line)
            continue
        is_item = bool(ITEM.match(raw))
        text = _clean(raw)
        if len(text) < 12:
            continue
        if text.endswith("?"):
            # une phrase de contexte suivie d'une question : seule la question est gardée
            parts = re.split(r"(?<=[.!])\s+(?=[A-ZÀ-Ý])", text)
            out.append(parts[-1] if parts[-1].endswith("?") and len(parts[-1]) >= 12 else text)
        elif is_item and in_list:
            out.append(text)
        if CONTEXT.search(line) and (line.endswith(":") or not text.endswith("?")):
            in_list = True
    seen, unique = set(), []
    for q in out:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            unique.append(q)
    return unique


def frame(body: str) -> dict[str, str]:
    """Forme du mail (pour les mails types) : salutation, phrase d'introduction, formule de fin. Jamais les questions."""
    lines = [l.strip() for l in new_part(body).split("\n")]
    greeting = next((l for l in lines if GREETING.match(l)), "")
    closing = next((l for l in lines if SIGN.match(l)), "")
    intro = ""
    for l in lines:
        if not l or GREETING.match(l) or l.endswith("?") or ITEM.match(l):
            if intro and (l.endswith("?") or ITEM.match(l)):
                break
            continue
        if SIGN.match(l):
            break
        intro = (intro + " " + l).strip()
        if l.endswith(":"):
            break
    return {"greeting": greeting[:80], "intro": intro[:400], "closing": closing[:80]}


# ==================================================================================== FIN DE LA COPIE DE extract.py
# ---------------------------------------------------------------------------------------------- réglages
TEAM = os.environ.get("CONTACTS_TEAM_ADDRESS", "AmeuRFPteam")  # adresse (ou nom) de l'équipe RFP en copie
MONTHS = 36                      # période lue
GLOSSARY = "glossaire"           # le fichier Excel est déposé dans le dossier SharePoint qui contient ce fichier
DESTINATION = ""                 # ou un dossier imposé (chemin complet), prioritaire
# Dossier SharePoint du glossaire, relatif au profil (identique sur tous les postes une fois la bibliothèque synchronisée)
SHAREPOINT = Path("Rothschild & Co") / "AM-RFP-CONF - Documents" / "7 - Ressources" / "Stagiaire" / "Passation stagiaires" / "poubelle Noa" / "Glossaire .PY"
PR_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
VERSION = 1


def say(msg: str = "") -> None:
    print(f"  {msg}", flush=True)


def excel_questions(path: Path) -> list[str]:
    """Questions d'une pièce jointe Excel (rare) : cellules qui finissent par « ? », ou colonne intitulée « Question »."""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        out = []
        for ws in wb.worksheets:
            qcol = None
            for r, row in enumerate(ws.iter_rows(values_only=True)):
                if r > 2000:
                    break
                cells = [str(c).strip() if c is not None else "" for c in row]
                if qcol is None:
                    qcol = next((i for i, c in enumerate(cells) if c.lower() in ("question", "questions", "question(s)")), None)
                    if qcol is not None:
                        continue
                for i, c in enumerate(cells):
                    if len(c) >= 12 and (c.endswith("?") or (qcol is not None and i == qcol)):
                        out.append(" ".join(c.split()))
        return list(dict.fromkeys(out))[:300]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------------------------- Outlook
class Reader:
    def __init__(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        self.ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        self.people: dict[str, dict] = {}

    def person(self, entry, name="", email=""):
        k = (email or name).lower()
        if k in self.people:
            return self.people[k]
        dept, is_list = "", False
        try:
            u = entry.GetExchangeUser() if entry is not None else None
            if u is not None:
                name, email, dept = u.Name or name, u.PrimarySmtpAddress or email, u.Department or ""
            elif entry is not None and entry.GetExchangeDistributionList() is not None:
                dl = entry.GetExchangeDistributionList()
                name, email, is_list = dl.Name or name, dl.PrimarySmtpAddress or email, True
        except Exception:  # noqa: BLE001
            pass
        if (not email or "@" not in email) and entry is not None:
            try:
                email = entry.PropertyAccessor.GetProperty(PR_SMTP)
            except Exception:  # noqa: BLE001
                pass
        p = {"name": name, "email": (email or "").lower(), "department": dept, "list": is_list}
        if k:
            self.people[k] = p
        return p

    def members(self) -> list[str]:
        try:
            r = self.ns.CreateRecipient(TEAM)
            r.Resolve()
            dl = r.AddressEntry.GetExchangeDistributionList()
            return sorted({m.GetExchangeUser().PrimarySmtpAddress.lower() for m in dl.GetExchangeDistributionListMembers()
                           if m.GetExchangeUser() is not None})
        except Exception:  # noqa: BLE001
            return []

    def folders(self, root):
        stack = [root]
        while stack:
            f = stack.pop()
            yield f
            try:
                stack.extend(list(f.Folders))
            except Exception:  # noqa: BLE001
                pass

    def mails(self, since: datetime):
        t = TEAM.replace("'", "''")
        dasl = ("@SQL=(\"urn:schemas:httpmail:displayto\" LIKE '%{t}%' OR \"urn:schemas:httpmail:displaycc\" LIKE '%{t}%') "
                "AND \"urn:schemas:httpmail:datereceived\" >= '{w}'").format(t=t, w=since.strftime("%Y-%m-%d %H:%M"))
        seen, tmp = set(), Path(tempfile.mkdtemp(prefix="collecte-"))
        for store in list(self.ns.Stores):
            try:
                root = store.GetRootFolder()
            except Exception:  # noqa: BLE001
                continue
            for folder in self.folders(root):
                try:
                    if folder.DefaultItemType != 0:
                        continue
                    items = folder.Items.Restrict(dasl)
                except Exception:  # noqa: BLE001
                    continue
                for item in items:
                    try:
                        if item.Class != 43 or item.EntryID in seen:
                            continue
                        seen.add(item.EntryID)
                        m = self.mail(item, tmp)
                        if m["questions"]:
                            yield m
                    except Exception:  # noqa: BLE001
                        continue

    def mail(self, item, tmp: Path) -> dict:
        body = item.Body or ""
        qs = questions(body)
        files = []
        for att in item.Attachments:
            n = att.FileName or ""
            if n.lower().endswith((".xlsx", ".xlsm")):
                target = tmp / n
                try:
                    att.SaveAsFile(str(target))
                    found = excel_questions(target)
                    if found:
                        qs += found
                        files.append(n)
                except Exception:  # noqa: BLE001
                    pass
                finally:
                    target.unlink(missing_ok=True)
        if not qs:
            return {"questions": []}
        to, cc = [], []
        for r in item.Recipients:
            (to if r.Type == 1 else cc if r.Type == 2 else []).append(self.person(r.AddressEntry, r.Name or "", r.Address or ""))
        s = item.SentOn
        return {"id": hashlib.sha1(item.EntryID.encode()).hexdigest()[:16], "subject": item.Subject or "",
                "date": f"{s.year:04d}-{s.month:02d}-{s.day:02d}" if s else "",
                "sender": self.person(getattr(item, "Sender", None), item.SenderName or "", item.SenderEmailAddress or ""),
                "to": to, "cc": cc, "questions": qs, "attachments": files, "frame": frame(body)}


# ---------------------------------------------------------------------------------------------- glossaire
# Mêmes règles que l'app (backend/merlin/contacts/inventory.py), en version autonome.
DD_TYPES = [
    ("ESG / opérationnelle", ["esg", "isr", "sfdr", "pai", "taxonomie", "durabilite", "sustainability", "climat", "climate", "pri", "odd",
                              "operational due diligence", "due diligence operationnelle", "operationnelle", "operational",
                              "cybersecurite", "cybersecurity", "bcp", "continuite"]),
    ("Consultant", ["consultant", "mercer", "aon", "willis towers watson", "wtw", "bfinance", "cambridge associates", "russell investments",
                    "morningstar", "fundsquare", "selecteur", "selector", "manager research", "gatekeeper", "rfp consultant"]),
    ("Distributeur", ["distributeur", "distributor", "distribution", "plateforme", "platform", "banque privee", "private bank", "cgp",
                      "conseiller en gestion", "allfunds", "fundsettle", "selection de fonds", "fund selection", "wealth", "gestion privee",
                      "assurance vie", "unite de compte"]),
    ("Institutionnel", ["institutionnel", "institutional", "assureur", "insurer", "mutuelle", "caisse", "pension", "retraite",
                        "fonds de pension", "pension fund", "prevoyance", "family office", "fondation", "endowment", "appel d'offres",
                        "appel d offres", "tender", "mandat"]),
]
DEFAULT_INTRO = "Dans le cadre d'une due diligence pour {client}, pourriez-vous nous aider à répondre aux questions suivantes ?"
NUMBERING = re.compile(r"^\s*(?:(?:q(?:uestion)?|n°|no\.?)\s*\d+[a-z]?\s*[.):-]?\s+|\d+(?:\.\d+)*[.)]\s+|\d+(?:\.\d+)+\s+|[a-z][).]\s+)", re.I)
MASTER = "Glossaire qui contacter.xlsx"


def fold(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def qkey(question: str) -> str:
    return " ".join(re.sub(r"[^\w%]+", " ", fold(NUMBERING.sub("", question or ""))).split())


def dd_type(*texts: str) -> str:
    t = " " + " ".join(re.sub(r"[^\w]+", " ", fold(x or "")) for x in texts) + " "
    for label, words in DD_TYPES:
        if any(f" {w} " in t for w in words):
            return label
    return "Non classé"


def asks(mails: list[dict], members: set[str]) -> list[dict]:
    """Une demande = mail d'un membre de l'équipe RFP avec des questions ; contacts = destinataires internes hors équipe."""
    tok = fold(TEAM)
    is_team = lambda p: tok in fold(p.get("name", "")) or tok in fold(p.get("email", "")) or p.get("email") in members  # noqa: E731
    if not members:
        members = {m["sender"]["email"] for m in mails if m.get("questions") and m["sender"].get("email")}
    doms = [m["sender"]["email"].rsplit("@", 1)[-1] for m in mails if m["sender"].get("email") in members and "@" in m["sender"]["email"]]
    house = max(set(doms), key=doms.count) if doms else ""
    out = []
    for m in mails:
        if m["sender"].get("email") not in members or not m.get("questions"):
            continue
        people = [p for p in m["to"] if not is_team(p) and not p.get("list")] or [p for p in m["cc"] if not is_team(p) and not p.get("list")]
        internal = [p for p in people if p.get("department") or (house and p.get("email", "").endswith("@" + house))]
        if not internal:
            continue
        dd = dd_type(m["subject"], " ".join(m.get("attachments", [])), " ".join(m["questions"][:5]))
        for q in m["questions"]:
            out.append({"question": q, "date": m.get("date", ""), "subject": m["subject"], "dd": dd, "frame": m.get("frame", {}),
                        "contacts": [{"name": p.get("name", ""), "email": p.get("email", ""), "department": p.get("department", "")} for p in internal]})
    return out


def _tri(k: str) -> set[str]:
    t = f"  {k}  "
    return {t[i:i + 3] for i in range(len(t) - 2)}


def groups(items: list[dict]) -> list[dict]:
    """Même question posée plusieurs fois : regroupée (trigrammes de caractères, recherche par mots rares)."""
    by_key: dict[str, list[dict]] = {}
    for a in items:
        k = qkey(a["question"])
        if len(k) >= 8:
            by_key.setdefault(k, []).append(a)
    keys = list(by_key)
    tris = [_tri(k) for k in keys]
    words = [set(k.split()) for k in keys]
    df: dict[str, int] = {}
    for ws in words:
        for w in ws:
            df[w] = df.get(w, 0) + 1
    index: dict[str, list[int]] = {}
    for i, ws in enumerate(words):
        for w in sorted(ws, key=lambda w: df[w])[:3]:
            index.setdefault(w, []).append(i)
    parent = list(range(len(keys)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(keys)):
        cands = {j for w in sorted(words[i], key=lambda w: df[w])[:3] for j in index.get(w, []) if j != i}
        for j in cands:
            if 2 * len(tris[i] & tris[j]) / (len(tris[i]) + len(tris[j])) >= 0.8:
                parent[find(i)] = find(j)
    clusters: dict[int, list[str]] = {}
    for i, k in enumerate(keys):
        clusters.setdefault(find(i), []).append(k)
    out = []
    for ks in clusters.values():
        its = [a for k in ks for a in by_key[k]]
        variants: dict[str, int] = {}
        teams: dict[str, int] = {}
        people: dict[str, int] = {}
        dds: dict[str, int] = {}
        for a in its:
            variants[a["question"]] = variants.get(a["question"], 0) + 1
            dds[a["dd"]] = dds.get(a["dd"], 0) + 1
            for c in a["contacts"]:
                t = c.get("department") or "Service inconnu"
                teams[t] = teams.get(t, 0) + 1
                p = f"{c['name']} <{c['email']}>" if c.get("email") else c.get("name", "")
                people[p] = people.get(p, 0) + 1
        srt = lambda d: sorted(d.items(), key=lambda kv: -kv[1])  # noqa: E731
        team = srt(teams)[0][0] if teams else ""
        share = teams.get(team, 0) / (sum(teams.values()) or 1)
        out.append({"question": srt(variants)[0][0], "variants": [v for v, _ in srt(variants)], "times": len(its),
                    "last": max(a["date"] for a in its), "dd_types": dict(srt(dds)), "team": team, "team_share": round(share, 2),
                    "teams": dict(srt(teams)[:5]), "people": [p for p, _ in srt(people)[:4]],
                    "subjects": list(dict.fromkeys(a["subject"] for a in its))[:5],
                    "check": team in ("", "Service inconnu") or share < 0.6})
    return sorted(out, key=lambda g: (-g["times"], g["question"]))


def templates(items: list[dict]) -> dict[str, dict]:
    per: dict[str, list[dict]] = {}
    seen = set()
    for a in items:
        if (a["subject"], a["date"]) in seen:
            continue
        seen.add((a["subject"], a["date"]))
        for t in {c.get("department") or "Service inconnu" for c in a["contacts"]}:
            per.setdefault(t, []).append(a.get("frame") or {})
    out = {}
    for t, frames in per.items():
        def most(f: str, minimum: int, default: str) -> str:
            c: dict[str, int] = {}
            for fr in frames:
                v = (fr.get(f) or "").strip()
                if v:
                    c[v] = c.get(v, 0) + 1
            best = max(c.items(), key=lambda kv: kv[1]) if c else None
            return best[0] if best and best[1] >= minimum else default
        out[t] = {"greeting": most("greeting", 1, "Bonjour,"), "intro": most("intro", 2, DEFAULT_INTRO),
                  "closing": most("closing", 1, "Merci d'avance,"), "mails": len(frames)}
    return out


def draft(t: dict, qs: list[str]) -> str:
    return "\n".join([t["greeting"], "", t["intro"].replace("{client}", "[client]"), "", *[f"{i}. {q}" for i, q in enumerate(qs, 1)], "", t["closing"]])


def read_collect(path: Path) -> tuple[dict, list[dict]] | None:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(path, read_only=True)
        info = {str(r[0]): r[1] for r in wb["Infos"].iter_rows(values_only=True) if r and r[0]}
        if info.get("format") != "collecte-qui-contacter":
            return None
        mails = [json.loads(r[1]) for r in wb["Mails"].iter_rows(min_row=2, values_only=True) if r and r[1]]
        return info, mails
    except Exception:  # noqa: BLE001 - fichier ouvert ou abîmé : ignoré
        return None


def corrections(master: Path) -> dict[str, tuple[str, str]]:
    """Corrections faites à la main dans le glossaire : reprises à chaque reconstruction."""
    from openpyxl import load_workbook

    if not master.exists():
        return {}
    try:
        ws = load_workbook(master, read_only=True)["Questions"]
        rows = ws.iter_rows(values_only=True)
        head = [str(h or "") for h in next(rows)]
        qi, ti, pi = head.index("Question"), head.index("Équipe (corrigée)"), head.index("Personnes (corrigées)")
        return {qkey(str(r[qi])): (str(r[ti] or "").strip(), str(r[pi] or "").strip()) for r in rows if r and r[qi] and (r[ti] or r[pi])}
    except Exception:  # noqa: BLE001
        return {}


def build_glossary(folder: Path) -> tuple[Path, int, int]:
    """Glossaire commun : toutes les collectes du dossier « Collectes », un mail vu dans deux boîtes compté une fois."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    all_asks, seen, sources = [], set(), []
    for f in sorted((folder / "Collectes").glob("Collecte_*.xlsx")):
        got = read_collect(f)
        if not got:
            continue
        info, mails = got
        mails = [m for m in mails if m.get("id") not in seen]
        seen |= {m.get("id") for m in mails}
        all_asks += asks(mails, set(json.loads(info.get("membres_equipe") or "[]")))
        sources.append(f"{info.get('collecte_par')} ({str(info.get('date') or '')[:10]})")
    master = folder / MASTER
    fixes = corrections(master)
    gs = groups(all_asks)
    for g in gs:
        fix = fixes.get(qkey(g["question"]))
        g["fix"] = fix or ("", "")
        if fix:
            g["check"] = False
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    head = ["Question", "Équipe", "Personnes", "Nb de fois", "Dernière fois", "Types de due diligence", "Part de l'équipe",
            "Autres équipes", "Variantes", "Objets des mails", "À vérifier", "Équipe (corrigée)", "Personnes (corrigées)"]
    ws.append(head)
    for g in gs:
        ws.append([g["question"], g["fix"][0] or g["team"], g["fix"][1] or "\n".join(g["people"]), g["times"], g["last"],
                   ", ".join(f"{k} ({v})" for k, v in g["dd_types"].items()), g["team_share"],
                   ", ".join(f"{k} ({v})" for k, v in g["teams"].items() if k != g["team"]), "\n".join(g["variants"][1:8]),
                   "\n".join(g["subjects"]), "oui" if g["check"] else "", g["fix"][0], g["fix"][1]])
    yellow = PatternFill("solid", fgColor="FFFF00")
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if row[10].value == "oui":
            row[10].fill = yellow
    for i, w in enumerate([70, 24, 40, 10, 14, 30, 12, 30, 60, 50, 10, 24, 40]):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    by_team: dict[str, list[dict]] = {}
    for g in gs:
        by_team.setdefault(g["fix"][0] or g["team"], []).append(g)
    t = wb.create_sheet("Par équipe")
    t.append(["Équipe", "Questions", "Fois demandées", "Personnes"])
    for team, items in sorted(by_team.items(), key=lambda kv: -sum(g["times"] for g in kv[1])):
        people: dict[str, int] = {}
        for g in items:
            for p in g["people"]:
                people[p] = people.get(p, 0) + 1
        t.append([team, len(items), sum(g["times"] for g in items), "\n".join(sorted(people, key=lambda p: -people[p])[:6])])
    d = wb.create_sheet("Par type de due diligence")
    d.append(["Type de due diligence", "Question", "Équipe", "Nb de fois"])
    for g in gs:
        for k, v in g["dd_types"].items():
            d.append([k, g["question"], g["fix"][0] or g["team"], v])
    m = wb.create_sheet("Mails types")
    m.append(["Équipe", "Salutation", "Introduction", "Formule de fin", "Mails analysés", "Exemple"])
    for team, v in templates(all_asks).items():
        m.append([team, v["greeting"], v["intro"], v["closing"], v["mails"], draft(v, ["(question 1)", "(question 2)"])])
    s = wb.create_sheet("Sources")
    s.append(["Boîtes lues", "Construit le"])
    for src in sources:
        s.append([src, datetime.now().strftime("%Y-%m-%d %H:%M")])
    for sheet in wb.worksheets:
        for c in sheet[1]:
            c.font = Font(bold=True)
        if sheet.title != "Questions":
            for col in "ABCDEF":
                sheet.column_dimensions[col].width = 40
    tmp = master.with_name("~tmp_" + master.name)
    wb.save(tmp)
    try:
        os.replace(tmp, master)
    except PermissionError:  # glossaire ouvert dans Excel : nouvelle version à côté, jamais d'écrasement forcé
        master = master.with_name(f"Glossaire qui contacter ({datetime.now():%Y-%m-%d %H%M}).xlsx")
        os.replace(tmp, master)
    return master, len(gs), len(sources)


# ---------------------------------------------------------------------------------------------- destination
def destination() -> Path:
    """Le dossier SharePoint du glossaire : celui du .bat s'il le contient, sinon recherche dans les dossiers
    synchronisés (OneDrive / SharePoint) du poste ; sinon le Bureau."""
    if DESTINATION:
        return Path(DESTINATION)
    # dossier du .bat (le script est extrait du .bat dans le profil : son propre dossier ne compte pas)
    here = Path(os.environ.get("COLLECTE_DIR") or Path(__file__).resolve().parent).resolve()
    if GLOSSARY in here.name.lower() or any(GLOSSARY in p.name.lower() for p in here.iterdir()):
        return here  # le .bat est lancé depuis le dossier du glossaire : le fichier va à côté
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    if (home / SHAREPOINT).is_dir():
        return home / SHAREPOINT  # même dossier SharePoint, sur n'importe quel poste
    roots = [Path(v) for k, v in os.environ.items() if k.upper().startswith("ONEDRIVE") and v]
    roots += [p for p in home.iterdir() if p.is_dir() and (" - " in p.name or p.name.lower().startswith("onedrive"))] if home.exists() else []
    for root in dict.fromkeys(roots):
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if dirpath.count(os.sep) - str(root).count(os.sep) > 6:
                    dirnames[:] = []
                    continue
                if any(GLOSSARY in f.lower() and not f.startswith("~$") for f in filenames):
                    return Path(dirpath)
        except OSError:
            continue
    return home / "Desktop"


def write(mails: list[dict], members: list[str], months: int) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    user = os.environ.get("USERNAME") or getpass.getuser()
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(["Date", "Objet du mail", "Destinataires", "Question"])
    for m in mails:
        dest = ", ".join(f"{p['name']} ({p['department'] or '?'})" for p in m["to"] + m["cc"] if not p.get("list"))
        for q in m["questions"]:
            ws.append([m["date"], m["subject"], dest, q])
    for col, w in zip("ABCD", (12, 50, 50, 90)):
        ws.column_dimensions[col].width = w
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    data = wb.create_sheet("Mails")  # lu par l'app (Qui contacter › Importer une collecte) : ne pas modifier
    data.append(["mail", "json"])
    for m in mails:
        data.append([m["id"], json.dumps(m, ensure_ascii=False)[:32000]])
    info = wb.create_sheet("Infos")
    for k, v in {"format": "collecte-qui-contacter", "version": VERSION, "collecte_par": user, "date": datetime.now().isoformat(timespec="seconds"),
                 "periode_mois": months, "equipe": TEAM, "membres_equipe": json.dumps(members), "mails": len(mails),
                 "questions": sum(len(m["questions"]) for m in mails)}.items():
        info.append([k, v])
    folder = destination() / "Collectes"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"Collecte_{user}.xlsx"  # une par personne, remplacée à chaque lancement
    tmp = target.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    os.replace(tmp, target)
    return target


def rebuild_bat() -> None:
    """Après une modification de ce fichier : python collecte.py --construire (remet le script dans le .bat)."""
    bat = Path(__file__).with_name("Collecte_Qui_Contacter.bat")
    marker = "#" + "__PYTHON__"
    head = bat.read_text(encoding="utf-8").replace("\r\n", "\n").split(marker, 1)[0].rstrip()
    bat.write_text(head + "\n" + marker + "\n" + Path(__file__).read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n")
    print("Collecte_Qui_Contacter.bat reconstruit")


def main() -> int:
    if "--construire" in sys.argv:
        rebuild_bat()
        return 0
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    months = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else MONTHS
    say("Collecte « Qui contacter » — équipe RFP")
    say("")
    say(f"Lu dans votre Outlook : les mails des {months} derniers mois avec {TEAM} en destinataire ou en copie.")
    say("Gardé : la date, l'objet, les destinataires (nom, adresse, service) et les questions posées.")
    say("Jamais gardé : le corps des mails, les réponses, les pièces jointes. Rien n'est modifié dans Outlook.")
    say("")
    if "--oui" not in sys.argv:
        try:
            input("  Appuyez sur Entrée pour lancer (ou fermez la fenêtre pour annuler)… ")
        except EOFError:
            pass
    try:
        reader = Reader()
    except Exception:  # noqa: BLE001
        say("Outlook ne répond pas. Ouvrez Outlook classique (pas le « nouvel Outlook »), puis relancez.")
        return 1
    members = reader.members()
    mails, t0 = [], time.time()
    for m in reader.mails(datetime.now() - timedelta(days=int(months * 30.5))):
        mails.append(m)
        if len(mails) % 25 == 0:
            say(f"{len(mails)} mails avec des questions trouvés…")
    target = write(mails, members, months)
    say("Construction du glossaire…")
    master, n_questions, n_sources = build_glossary(target.parent.parent)
    say("")
    say(f"Terminé en {int(time.time() - t0)} s : {len(mails)} mails, {sum(len(m['questions']) for m in mails)} questions lues.")
    say(f"Glossaire : {master}")
    say(f"  {n_questions} questions distinctes, {n_sources} boîte(s) lue(s).")
    if master.parent.name.lower() == "desktop":
        say("Le dossier SharePoint « Glossaire .PY » n'a pas été trouvé : déposez le glossaire et le dossier Collectes dans ce dossier.")
    try:
        os.startfile(str(master))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
