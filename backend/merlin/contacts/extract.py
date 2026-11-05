"""Questions d'un mail : seulement ce que l'équipe RFP a écrit (historique cité et signature retirés), découpé en
questions. Les réponses des autres équipes ne sont jamais lues (elles changent à chaque fois)."""
from __future__ import annotations

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


def excel_questions(path: Path) -> list[str]:
    """Questions d'une pièce jointe Excel (rare) : lues avec le lecteur des RFI, cases réponse vides ou non."""
    try:
        from ..rfi.layout import detect

        return [s.question for s in detect(path).slots if (s.question or "").strip()][:300]
    except Exception:  # noqa: BLE001 - pièce jointe illisible : ignorée
        return []


__all__ = ["questions", "new_part", "excel_questions", "frame"]
