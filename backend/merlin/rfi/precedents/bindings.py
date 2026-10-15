"""Liaisons apprises : quelle colonne Fabric (ou quel champ du DIC / prospectus) se cachait derrière une question.

Pour chaque question posée à plusieurs fonds dans les anciens RFI, on compare la réponse donnée à CHAQUE colonne
Product Info du fonds concerné (et aux champs de ses documents officiels en cache). Une liaison n'est retenue que si :
  - elle est vérifiée sur au moins 3 fonds, avec au moins 90 % de concordance ;
  - aucune autre colonne n'explique aussi bien les réponses (sinon : « ambiguë », jamais utilisée) ;
  - les réponses ou les valeurs varient d'un fonds à l'autre (une colonne constante « explique » tout : « faible »).
Seules les colonnes du catalogue sont testées : aucun nom n'est deviné.

  cd backend && python -m merlin.rfi.precedents.bindings      (construit data/rfi/bindings.json, jamais committé)
"""
from __future__ import annotations

import json
import re
import sys
import threading
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..layout import classify_cell
from ..ontology import Concept, Ontology, norm, parse_term
from ..values import PRODUCT, SHARE, is_empty
from .compare import NOT_ANSWERS, same
from .store import PrecedentStore

MIN_SUPPORT, MIN_RATE, AUTO_SUPPORT = 3, 0.9, 5
SKIP_COLUMNS = re.compile(r"(?i)(^id$|guid|createdon|modifiedon|created_by|modified_by|statecode|statuscode|versionnumber|"
                          r"owner|_by_delegate|timezone|importsequence|overriddencreatedon|^pi_|productid$|shareid$)")


@dataclass
class Binding:
    question: str
    qnorm: str
    target: str  # « PI_OUT_Share.Swing_Pricing », « doc:kid.sri »
    label: str
    type: str
    support: int
    compared: int
    rate: float
    status: str = "candidate"  # candidate | validated | rejected | ambiguous | weak
    runner_up: str = ""
    examples: list[str] = field(default_factory=list)  # provenance seulement (fichier · cellule · fonds)
    built_at: str = ""

    @property
    def id(self) -> str:
        return f"{self.qnorm[:80]}→{self.target}"

    @property
    def usable(self) -> bool:
        return self.status in {"candidate", "validated"}

    @property
    def strong(self) -> bool:
        return self.status == "validated" or (self.support >= AUTO_SUPPORT and self.rate == 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "id": self.id, "usable": self.usable, "strong": self.strong}


def _ptype(column) -> str:
    if column.data_type == "bit":
        return "bool"
    if column.kind == "number":
        return "number"
    if column.kind in {"date", "datetime"}:
        return "date"
    return "text"


def pseudo_concept(target: str, ctype: str, ontology: Ontology) -> Concept:
    """Concept minimal pour lire / rendre une colonne qui n'est pas (encore) dans l'ontologie."""
    for c in ontology.concepts.values():
        if isinstance(c.source, str) and c.source == target:
            return c  # colonne déjà couverte : on garde son vocabulaire, ses bornes, sa mise en forme
    table, _, column = target.partition(".")
    return Concept(id=f"pi:{target}", label_fr=f"{column} (colonne {table})", label_en=f"{column} ({table})",
                   scope="share" if table == SHARE else "fund", type=ctype, source=target, terms=[parse_term(column.lower())])


class BindingMiner:
    def __init__(self, data, ontology: Ontology, store: PrecedentStore, resolver, documents=None):
        self.data, self.ontology, self.store, self.resolver, self.documents = data, ontology, store, resolver, documents

    def _compare(self, concept: Concept, value, answer) -> str:
        r = same(self.ontology, concept, value, answer)
        if r != "match" and concept.type == "number":
            # colonne décimale : le RFI a pu l'écrire en % (1,35 %) ou en fraction (0,0135)
            r2 = same(self.ontology, Concept(id="x", label_fr="", label_en="", scope="fund", type="percent", source="", terms=[]), value, answer)
            r = "match" if r2 == "match" else r
        if r != "match" and concept.type == "text":
            a, b = self.ontology.vocab_value("yes_no", value), self.ontology.vocab_value("yes_no", answer)
            if a is not None and b is not None:  # colonne texte « Yes » et réponse « Oui »
                r = "match" if a.id == b.id else "mismatch"
        return r

    def _rows(self) -> tuple[dict[str, dict], dict[str, dict], list[tuple[str, str, str]]]:
        cols: list[tuple[str, str, str]] = []  # (table, colonne, type)
        products, shares = {}, {}
        for table, key, sink in ((PRODUCT, "pi_productid", products), (SHARE, "ISIN_Code", shares)):
            t = self.data.catalog.table(table)
            if t is None:
                continue
            names = [c.name for c in t.columns if not SKIP_COLUMNS.search(c.name) or c.name == key]
            cols += [(table, c.name, _ptype(c)) for c in t.columns if not SKIP_COLUMNS.search(c.name)]
            alias = "p" if table == PRODUCT else "s"
            frame = self.data.query(f"SELECT {', '.join(f'{alias}.{n}' for n in names)} FROM dbo.{table} {alias}", {})
            for row in frame.to_dict("records"):
                if not is_empty(row.get(key)):
                    sink.setdefault(str(row[key]).upper() if table == SHARE else str(row[key]), row)
        return products, shares, cols

    def build(self) -> list[Binding]:
        products, shares, columns = self._rows()
        groups: dict[str, list] = defaultdict(list)
        for p in self.store.all():
            if p.kind not in {"answer", "checkbox"} or p.blocked or p.empty or norm(p.answer_text) in NOT_ANSWERS:
                continue
            if classify_cell(p.answer_text)[0] != "answered" or len(p.answer_text) > 200:
                continue
            groups[norm(p.question)].append(p)
        out: list[Binding] = []
        now = datetime.now().isoformat(timespec="seconds")
        for qn, items in groups.items():
            per_fund = {}
            for p in sorted(items, key=lambda x: x.ref_date, reverse=True):
                ent = self.resolver.resolve(p.isin, p.fund_name, p.share_name)
                if ent is not None:
                    per_fund.setdefault((ent.pid, ent.isin), (ent, p))
            if len(per_fund) < MIN_SUPPORT:
                continue
            scores: list[tuple[int, int, str, str, list]] = []
            for table, column, ctype in columns:
                concept = pseudo_concept(f"{table}.{column}", ctype, self.ontology)
                ok = ko = 0
                values, examples = [], []
                for (pid, isin), (ent, p) in per_fund.items():
                    row = products.get(str(pid)) if table == PRODUCT else shares.get(str(isin or "").upper())
                    if row is None:
                        continue
                    value = row.get(column)
                    if is_empty(value):
                        continue
                    r = self._compare(concept, value, p.answer_raw)
                    if r == "match":
                        ok += 1
                        values.append(str(value))
                        examples.append(p.provenance())
                    elif r == "mismatch":
                        ko += 1
                if ok >= MIN_SUPPORT:
                    scores.append((ok, ko, f"{table}.{column}", concept.type, examples, values))
            # champs des documents officiels (cache seulement : la construction ne télécharge rien)
            if self.documents is not None:
                doc_scores = defaultdict(lambda: [0, 0, [], []])
                for (pid, isin), (ent, p) in per_fund.items():
                    if not isin:
                        continue
                    try:
                        facts = self.documents._facts.get(isin.upper(), ({}, [], []))[0] or {}
                    except Exception:  # noqa: BLE001
                        facts = {}
                    for name, fact in facts.items():
                        ctype = "number" if isinstance(fact.value, (int, float)) else "text"
                        r = same(self.ontology, pseudo_concept(f"doc.{name}", ctype, self.ontology), fact.value, p.answer_raw)
                        cell = doc_scores[name]
                        if r == "match":
                            cell[0] += 1
                            cell[2].append(p.provenance())
                            cell[3].append(str(fact.value))
                        elif r == "mismatch":
                            cell[1] += 1
                for name, (ok, ko, ex, vals) in doc_scores.items():
                    if ok >= MIN_SUPPORT:
                        scores.append((ok, ko, f"doc:{name}", "text", ex, vals))
            if not scores:
                continue
            scores.sort(key=lambda s: (s[0] / (s[0] + s[1]), s[0]), reverse=True)
            ok, ko, target, ctype, examples, values = scores[0]
            rate = ok / (ok + ko)
            if rate < MIN_RATE:
                continue
            status = "candidate"
            runner = next((s for s in scores[1:] if s[0] / (s[0] + s[1]) >= MIN_RATE and s[0] >= ok - 0), None)
            if runner is not None:
                status = "ambiguous"  # deux colonnes expliquent aussi bien les réponses : on ne choisit pas
            answers = {norm(p.answer_text) for _, p in per_fund.values()}
            if len(set(values)) <= 1 and len(answers) <= 1:
                status = "weak"  # tout le monde a la même réponse et la même valeur : rien ne prouve la colonne
            label = target if target.startswith("doc:") else pseudo_concept(target, ctype, self.ontology).label_fr
            out.append(Binding(question=items[0].question.strip(), qnorm=qn, target=target, label=label, type=ctype, support=ok,
                               compared=ok + ko, rate=round(rate, 3), status=status, runner_up=runner[2] if runner else "",
                               examples=examples[:5], built_at=now))
        return sorted(out, key=lambda b: (-b.support, b.question))


class BindingIndex:
    """Liaisons apprises en mémoire (data/rfi/bindings.json) ; statut validé / rejeté conservé entre deux constructions."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._mtime = -1.0
        self.items: dict[str, Binding] = {}

    def _load(self) -> None:
        mtime = self.path.stat().st_mtime if self.path.exists() else 0.0
        if mtime == self._mtime:
            return
        items = {}
        if self.path.exists():
            for d in json.loads(self.path.read_text(encoding="utf-8")):
                d.pop("id", None), d.pop("usable", None), d.pop("strong", None)
                b = Binding(**d)
                items[b.id] = b
        self.items, self._mtime = items, mtime

    def all(self) -> list[Binding]:
        with self._lock:
            self._load()
            return list(self.items.values())

    def save(self, bindings: list[Binding]) -> None:
        with self._lock:
            self._load()
            for b in bindings:  # une décision humaine survit à la reconstruction
                old = self.items.get(b.id)
                if old is not None and old.status in {"validated", "rejected"}:
                    b.status = old.status
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps([b.to_dict() for b in bindings], ensure_ascii=False, indent=1), encoding="utf-8")
            self._mtime = -1.0

    def set_status(self, binding_id: str, status: str) -> Binding | None:
        with self._lock:
            self._load()
            b = self.items.get(binding_id)
            if b is None:
                return None
            b.status = status
            self.path.write_text(json.dumps([x.to_dict() for x in self.items.values()], ensure_ascii=False, indent=1), encoding="utf-8")
            self._mtime = -1.0
            return b

    def lookup(self, question: str, similar=None) -> Binding | None:
        """Liaison utilisable pour cette question (même libellé, ou libellé quasi identique via la recherche)."""
        items = [b for b in self.all() if b.usable]
        by_q = {b.qnorm: b for b in items}
        qn = norm(question)
        if qn in by_q:
            return by_q[qn]
        if similar is not None:
            for hit in similar(question):
                b = by_q.get(norm(hit))
                if b is not None:
                    return b
        return None

    def columns(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for b in self.all():
            if b.usable and not b.target.startswith("doc:"):
                table, _, column = b.target.partition(".")
                out[table].add(column)
        return out


def _main(argv: list[str]) -> int:
    from ...config import get_settings
    from ...data.access import build_data_access
    from ..ontology import load_ontology
    from ..service import fund_directory
    from . import get_index
    from .advisor import FundResolver

    settings = get_settings()
    data = build_data_access()
    root = settings.data_dir / "rfi"
    store = get_index(root).store
    miner = BindingMiner(data, load_ontology(data.catalog), store, FundResolver(fund_directory(data)))
    bindings = miner.build()
    BindingIndex(root / "bindings.json").save(bindings)
    count = Counter(b.status for b in bindings)
    print(f"{len(bindings)} liaisons ({dict(count)}) · mode {data.mode} · {root / 'bindings.json'}")
    for b in bindings[:25]:
        print(f"  {b.status:9} {b.support:3}/{b.compared:<3} {b.target:55} ← {b.question[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
