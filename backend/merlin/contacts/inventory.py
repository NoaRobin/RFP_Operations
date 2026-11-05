"""Inventaire « qui contacter pour quelle question, sur quelle due diligence », construit à partir des mails envoyés
par l'équipe RFP (adresse de l'équipe en destinataire ou en copie).

- Une demande = un mail écrit par un membre de l'équipe RFP qui contient des questions ; les destinataires internes
  hors équipe RFP sont les personnes contactées ; leur équipe vient du **service de l'annuaire** (jamais devinée).
- Les clients (destinataires externes, sans service dans l'annuaire, autre domaine) ne sont jamais des contacts.
- Une même question posée de plusieurs façons est regroupée (n-grammes de caractères + recouvrement des mots).
- Les réponses ne sont jamais lues : elles changent à chaque due diligence.
- Le fichier Excel produit se corrige à la main ; réimporté, il devient la référence (corrections prioritaires).
"""
from __future__ import annotations

import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..match.matcher import key
from ..search.lexical import CharNgrams
from ..search.text import fold

GROUP_SIMILARITY = 0.8
MIN_SCORE = 0.45  # proximité minimale pour proposer une équipe (en dessous : « équipe inconnue »)
DEFAULT_INTRO = "Dans le cadre d'une due diligence pour {client}, pourriez-vous nous aider à répondre aux questions suivantes ?"


@lru_cache
def dd_rules() -> dict[str, Any]:
    return yaml.safe_load((Path(__file__).with_name("ddtypes.yaml")).read_text(encoding="utf-8"))


def dd_type(*texts: str) -> tuple[str, str]:
    t = " " + " ".join(re.sub(r"[^\w]+", " ", fold(x or "")) for x in texts) + " "
    rules = dd_rules()
    for r in rules["types"]:
        if any(f" {w} " in t for w in r["words"]):
            return r["id"], r["label"]
    return rules["fallback"]["id"], rules["fallback"]["label"]


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in (email or "") else ""


@dataclass
class Ask:
    question: str
    date: str
    subject: str
    dd: str
    dd_label: str
    contacts: list[dict[str, str]]
    frame: dict[str, str] = field(default_factory=dict)


@dataclass
class Group:
    question: str
    variants: list[str]
    asks: list[Ask]
    team: str = ""
    people: list[str] = field(default_factory=list)
    corrected: bool = False

    def public(self) -> dict[str, Any]:
        teams = Counter(c.get("department") or "Service inconnu" for a in self.asks for c in a.contacts)
        dd = Counter(a.dd_label for a in self.asks)
        people = Counter(f"{c['name']} <{c['email']}>" if c.get("email") else c.get("name", "") for a in self.asks for c in a.contacts)
        total = sum(teams.values()) or 1
        team = self.team or (teams.most_common(1)[0][0] if teams else "")
        share = teams.get(team, 0) / total if not self.corrected else 1.0
        return {"question": self.question, "variants": self.variants[:8], "times": len(self.asks),
                "last": max((a.date for a in self.asks), default=""), "dd_types": dict(dd.most_common()),
                "team": team, "team_share": round(share, 2), "teams": dict(teams.most_common(5)),
                "people": self.people or [p for p, _ in people.most_common(4)], "corrected": self.corrected,
                "subjects": list(dict.fromkeys(a.subject for a in self.asks))[:5],
                "check": (not self.corrected) and (team in ("", "Service inconnu") or share < 0.6)}


# ---------------------------------------------------------------------------------------------- construction
def asks_from_mails(mails: Iterable[dict[str, Any]], token: str, members: set[str]) -> tuple[list[Ask], dict[str, Any]]:
    mails = list(mails)
    tok = fold(token)

    def is_team(p: dict[str, Any]) -> bool:
        return tok in fold(p.get("name", "")) or tok in fold(p.get("email", "")) or (p.get("email") in members)

    if not members:  # liste de diffusion non lisible : l'équipe = ceux qui écrivent des questions avec l'adresse de l'équipe
        members = {m["sender"]["email"] for m in mails if m.get("questions") and m["sender"].get("email")}
    house = Counter(_domain(m["sender"]["email"]) for m in mails if m["sender"].get("email") in members).most_common(1)
    house_domain = house[0][0] if house else ""
    out: list[Ask] = []
    stats = Counter()
    for m in mails:
        stats["mails"] += 1
        if m["sender"].get("email") not in members or not m.get("questions"):
            stats["sans_demande"] += 1
            continue
        people = [p for p in m["to"] if not is_team(p) and not p.get("list")]
        if not people:
            people = [p for p in m["cc"] if not is_team(p) and not p.get("list")]
        internal = [p for p in people if p.get("department") or (_domain(p.get("email", "")) == house_domain and house_domain)]
        if not internal:
            stats["vers_client"] += 1  # demande envoyée au client ou sans destinataire interne
            continue
        dd, label = dd_type(m["subject"], " ".join(m.get("attachments", [])), " ".join(m["questions"][:5]))
        contacts = [{"name": p.get("name", ""), "email": p.get("email", ""), "department": p.get("department", "")} for p in internal]
        stats["demandes"] += 1
        for q in m["questions"]:
            out.append(Ask(q, m.get("date", ""), m["subject"], dd, label, contacts, m.get("frame", {})))
    return out, {**stats, "questions": len(out), "team_members": len(members)}


def group(asks: list[Ask]) -> list[Group]:
    """Même question posée plusieurs fois (autres mots, numérotation…) : un seul groupe."""
    by_key: dict[str, list[Ask]] = defaultdict(list)
    for a in asks:
        k = key(a.question)
        if len(k) >= 8:
            by_key[k].append(a)
    keys = list(by_key)
    parent = list(range(len(keys)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    if len(keys) > 1:
        grams = CharNgrams(keys)
        for i, k in enumerate(keys):
            for h in grams.score(k, 6):  # cosinus des n-grammes de caractères : variantes, fautes, articles
                if h.index != i and h.score >= GROUP_SIMILARITY:
                    parent[find(i)] = find(h.index)
    clusters: dict[int, list[str]] = defaultdict(list)
    for i, k in enumerate(keys):
        clusters[find(i)].append(k)
    groups = []
    for ks in clusters.values():
        items = [a for k in ks for a in by_key[k]]
        variants = Counter(a.question for a in items)
        groups.append(Group(variants.most_common(1)[0][0], [v for v, _ in variants.most_common()], items))
    return sorted(groups, key=lambda g: (-len(g.asks), g.question))


def templates(asks: list[Ask]) -> dict[str, dict[str, str]]:
    """Mail type par équipe : la salutation, l'introduction et la formule de fin les plus utilisées par l'équipe RFP
    vers cette équipe (une introduction n'est reprise que si elle a servi au moins deux fois, sinon texte neutre)."""
    per: dict[str, list[dict[str, str]]] = defaultdict(list)
    seen = set()
    for a in asks:
        sig = (a.subject, a.date)
        if sig in seen:
            continue
        seen.add(sig)
        for team in {c.get("department") or "Service inconnu" for c in a.contacts}:
            per[team].append(a.frame or {})
    out = {}
    for team, frames in per.items():
        def most(field_: str, minimum: int = 1, default: str = "") -> str:
            c = Counter((f.get(field_) or "").strip() for f in frames if (f.get(field_) or "").strip())
            best = c.most_common(1)
            return best[0][0] if best and best[0][1] >= minimum else default
        out[team] = {"greeting": most("greeting", 1, "Bonjour,"), "intro": most("intro", 2, DEFAULT_INTRO),
                     "closing": most("closing", 1, "Merci d'avance,"), "mails": len(frames)}
    return out


def draft(template: dict[str, str] | None, questions: list[str], client: str = "", fund: str = "", deadline: str = "") -> str:
    t = template or {"greeting": "Bonjour,", "intro": DEFAULT_INTRO, "closing": "Merci d'avance,"}
    intro = t["intro"].replace("{client}", client or "[client]")
    lines = [t["greeting"], "", intro]
    if fund:
        lines.append(f"Fonds concerné : {fund}.")
    lines.append("")
    lines += [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    lines.append("")
    if deadline:
        lines.append(f"Pourriez-vous nous répondre avant le {deadline} ?")
    lines.append(t["closing"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- inventaire
class Inventory:
    def __init__(self, path: Path):
        self.path = path  # data/contacts/inventory.json (jamais committé : noms de collaborateurs)
        self.data: dict[str, Any] = self._load()
        self._index = None

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"groups": [], "templates": {}, "stats": {}, "built_at": None, "corrections": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        self._index = None

    def rebuild(self, asks: list[Ask], stats: dict[str, Any]) -> None:
        corrections = self.data.get("corrections", {})
        groups = []
        for g in group(asks):
            fix = corrections.get(key(g.question))
            if fix:
                g.team, g.people, g.corrected = fix.get("team", ""), fix.get("people", []), True
            groups.append(g.public())
        self.data.update(groups=groups, templates=templates(asks), stats=stats, built_at=date.today().isoformat())
        self.save()

    # ------------------------------------------------------------------ sources (ma boîte + collectes des collègues)
    def sources_dir(self) -> Path:
        return self.path.parent / "sources"

    def save_source(self, name: str, payload: dict[str, Any]) -> None:
        d = self.sources_dir()
        d.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "_", name)[:80] or "source"
        tmp = d / f"{safe}.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / f"{safe}.json")

    def sources(self) -> list[dict[str, Any]]:
        out = []
        for f in sorted(self.sources_dir().glob("*.json")) if self.sources_dir().exists() else []:
            try:
                out.append({"file": f.stem, **json.loads(f.read_text(encoding="utf-8"))})
            except (OSError, ValueError):
                continue
        return out

    def rebuild_all(self, token: str) -> dict[str, Any]:
        """Toutes les boîtes lues (la mienne, celles des collègues) : un mail vu dans deux boîtes ne compte qu'une fois."""
        asks: list[Ask] = []
        stats: Counter = Counter()
        seen: set[str] = set()
        for src in self.sources():
            mails = [m for m in src.get("mails", []) if m.get("id") not in seen]
            seen |= {m.get("id") for m in mails}
            a, st = asks_from_mails(mails, src.get("team") or token, set(src.get("members") or []))
            asks += a
            stats.update({k: v for k, v in st.items() if isinstance(v, int)})
        stats["sources"] = len(self.sources())
        self.rebuild(asks, dict(stats))
        return self.summary()

    def import_collected(self, content: bytes) -> dict[str, Any] | None:
        """Fichier produit par outils/collecte_qui_contacter (poste d'un collègue). None : ce n'est pas une collecte."""
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True)
        if "Infos" not in wb.sheetnames or "Mails" not in wb.sheetnames:
            return None
        info = {str(r[0]): r[1] for r in wb["Infos"].iter_rows(values_only=True) if r and r[0]}
        if info.get("format") != "collecte-qui-contacter":
            return None
        mails = []
        for r in wb["Mails"].iter_rows(min_row=2, values_only=True):
            try:
                mails.append(json.loads(r[1]))
            except (TypeError, ValueError):
                continue
        by = str(info.get("collecte_par") or "collegue")
        self.save_source(f"collecte_{by}", {"by": by, "date": str(info.get("date") or ""), "team": str(info.get("equipe") or ""),
                                            "members": json.loads(info.get("membres_equipe") or "[]"), "mails": mails})
        return {"by": by, "mails": len(mails)}

    def summary(self) -> dict[str, Any]:
        groups = self.data.get("groups", [])
        teams = Counter(g["team"] for g in groups)
        dd = Counter(t for g in groups for t in g["dd_types"])
        return {"built_at": self.data.get("built_at"), "stats": self.data.get("stats", {}), "questions": len(groups),
                "asked": sum(g["times"] for g in groups), "teams": dict(teams.most_common()), "dd_types": dict(dd.most_common()),
                "to_check": sum(1 for g in groups if g.get("check")), "corrections": len(self.data.get("corrections", {})),
                "sources": [{"by": x.get("by", x["file"]), "date": x.get("date", ""), "mails": len(x.get("mails", []))} for x in self.sources()]}

    # ------------------------------------------------------------------ Excel
    def to_excel(self) -> bytes:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Questions"
        head = ["Question", "Équipe", "Personnes", "Nb de fois", "Dernière fois", "Types de due diligence", "Part de l'équipe",
                "Autres équipes", "Variantes", "Objets des mails", "À vérifier", "Équipe (corrigée)", "Personnes (corrigées)"]
        ws.append(head)
        for g in self.data.get("groups", []):
            ws.append([g["question"], g["team"], "\n".join(g["people"]), g["times"], g["last"],
                       ", ".join(f"{k} ({v})" for k, v in g["dd_types"].items()), g["team_share"],
                       ", ".join(f"{k} ({v})" for k, v in g["teams"].items() if k != g["team"]),
                       "\n".join(g["variants"][1:]), "\n".join(g["subjects"]), "oui" if g.get("check") else "",
                       g["team"] if g.get("corrected") else "", "\n".join(g["people"]) if g.get("corrected") else ""])
        widths = [70, 24, 40, 10, 14, 30, 12, 30, 60, 50, 10, 24, 40]
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        bold = Font(bold=True)
        for c in ws[1]:
            c.font = bold
        yellow = PatternFill("solid", fgColor="FFFF00")
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if row[10].value == "oui":
                row[10].fill = yellow
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        teams = wb.create_sheet("Par équipe")
        teams.append(["Équipe", "Questions", "Fois demandées", "Personnes"])
        by_team: dict[str, list[dict]] = defaultdict(list)
        for g in self.data.get("groups", []):
            by_team[g["team"]].append(g)
        for t, gs in sorted(by_team.items(), key=lambda kv: -sum(g["times"] for g in kv[1])):
            people = Counter(p for g in gs for p in g["people"])
            teams.append([t, len(gs), sum(g["times"] for g in gs), "\n".join(p for p, _ in people.most_common(6))])
        dd = wb.create_sheet("Par type de due diligence")
        dd.append(["Type de due diligence", "Question", "Équipe", "Nb de fois"])
        for g in self.data.get("groups", []):
            for t, n in g["dd_types"].items():
                dd.append([t, g["question"], g["team"], n])
        tpl = wb.create_sheet("Mails types")
        tpl.append(["Équipe", "Salutation", "Introduction", "Formule de fin", "Mails analysés", "Exemple"])
        for t, v in self.data.get("templates", {}).items():
            tpl.append([t, v["greeting"], v["intro"], v["closing"], v["mails"],
                        draft(v, ["(question 1)", "(question 2)"], "[client]", "[fonds]", "[date]")])
        for sheet in (teams, dd, tpl):
            for c in sheet[1]:
                c.font = bold
            for col in "ABCDEF":
                sheet.column_dimensions[col].width = 40
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def import_corrections(self, content: bytes) -> int:
        """Fichier corrigé à la main : colonnes « Équipe (corrigée) » / « Personnes (corrigées) » deviennent la référence."""
        from openpyxl import load_workbook

        ws = load_workbook(io.BytesIO(content), read_only=True)["Questions"]
        rows = ws.iter_rows(values_only=True)
        head = [str(h or "") for h in next(rows)]
        qi, ti, pi = head.index("Question"), head.index("Équipe (corrigée)"), head.index("Personnes (corrigées)")
        fixes = self.data.setdefault("corrections", {})
        n = 0
        for r in rows:
            if not r or not r[qi]:
                continue
            team, people = (r[ti] or "").strip(), [p.strip() for p in str(r[pi] or "").split("\n") if p.strip()]
            if team or people:
                fixes[key(str(r[qi]))] = {"team": team, "people": people}
                n += 1
        for g in self.data.get("groups", []):
            fix = fixes.get(key(g["question"]))
            if fix:
                g.update(team=fix["team"] or g["team"], people=fix["people"] or g["people"], corrected=True, check=False, team_share=1.0)
        self.save()
        return n

    # ------------------------------------------------------------------ qui contacter (compléteur RFI)
    def _matcher(self):
        """Index des variantes de questions déjà posées : BM25 (+ thésaurus) pour trouver, recouvrement des mots rares
        dans les deux sens et trigrammes de caractères pour juger. Pas de probabilité calibrée ici (trop peu de
        couples étiquetés) : un score de proximité, avec un seuil prudent."""
        if self._index is None:
            from ..search.lexical import BM25F, Field

            rows = [(i, v) for i, g in enumerate(self.data.get("groups", [])) for v in (g["variants"] or [g["question"]])]
            self._index = (BM25F([{"question": v} for _, v in rows], [Field("question", 1.0, 0.5)]), rows) if rows else None
        return self._index

    def who(self, question: str, min_score: float = MIN_SCORE) -> dict[str, Any] | None:
        from ..match.matcher import chars
        from ..search.lexical import query_vector
        from ..search.text import terms
        from ..search.thesaurus import expand

        idx = self._matcher()
        if idx is None or not question.strip():
            return None
        bm, rows = idx
        vec, seq = query_vector(question)
        if seq:
            extra, _, _ = expand(seq)
            for t, w in extra.items():
                vec[t] = max(vec.get(t, 0.0), w)
        qt = set(terms(question))
        top_idf = max(bm.idf.values(), default=1.0)

        def cover(a: set[str], b: set[str]) -> float:
            w = {t: bm.idf.get(t, top_idf) for t in a}
            return sum(v for t, v in w.items() if t in b) / (sum(w.values()) or 1.0)

        best = None
        for h in bm.score(vec, 10):
            gi, text = rows[h.index]
            ct = set(terms(text))
            score = 0.6 * min(cover(qt, ct), cover(ct, qt)) + 0.4 * chars(question, text)
            if best is None or score > best[0]:
                best = (score, gi)
        if best is None or best[0] < min_score:
            return None
        g = self.data["groups"][best[1]]
        return {"team": g["team"], "people": g["people"][:3], "score": round(best[0], 2), "asked_as": g["question"],
                "times": g["times"], "last": g["last"]}

    def ask_plan(self, questions: list[str], client: str = "", fund: str = "", deadline: str = "") -> dict[str, Any]:
        """Questions sans réponse → une demande par équipe, avec le mail type de cette équipe prêt à copier."""
        by_team: dict[str, dict[str, Any]] = {}
        unknown = []
        for q in questions:
            w = self.who(q)
            if w is None or w["team"] in ("", "Service inconnu"):
                unknown.append(q)
                continue
            t = by_team.setdefault(w["team"], {"team": w["team"], "people": [], "questions": [], "matches": []})
            t["questions"].append(q)
            t["matches"].append(w)
            t["people"] = list(dict.fromkeys(t["people"] + w["people"]))[:4]
        tpl = self.data.get("templates", {})
        teams = []
        for t in sorted(by_team.values(), key=lambda x: -len(x["questions"])):
            t["mail"] = draft(tpl.get(t["team"]), t["questions"], client, fund, deadline)
            t["to"] = "; ".join(p.split("<")[-1].rstrip(">") if "<" in p else p for p in t["people"])
            teams.append(t)
        return {"teams": teams, "unknown": unknown, "built_at": self.data.get("built_at")}


__all__ = ["Inventory", "Ask", "asks_from_mails", "group", "templates", "draft", "dd_type"]
