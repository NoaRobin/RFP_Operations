"""Valeurs des concepts pour un fonds (pi_productid) et une part (ISIN), à une date d'arrêté.

Chaque valeur est accompagnée de sa preuve (table.colonne ou calcul, date de la donnée) pour la revue humaine.
Règles de rattachement reprises d'App4everyone :
  - part : PI_OUT_Share.ISIN_Code (+ ProductID = pi_productid si le fonds est connu) ; plusieurs lignes contradictoires
    pour le même ISIN → aucune valeur (jamais de choix arbitraire) ;
  - JUMP : ID_PI_PART = pi_shareid, à défaut CODE_ISIN_PART = ISIN ; fonds : ID_PI_FONDS = pi_productid.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from ..data.access import DataAccess, DataError
from . import perf as P
from .ontology import Concept, Ontology
from .understand import Period, Understanding

# Labels présents dans Product Info (liste incomplète : un « non » ne peut pas être affirmé à partir d'elle)
LABEL_COLUMNS = {"RSI_french_label": "ISR", "Belgium_Towards_Sustainability_label": "Towards Sustainability", "Finansol_Label": "Finansol"}
# Coûts de transaction du DIC (PRIIPs) = explicites + implicites, moyennes 3 ans ex ante — À CONFIRMER avec l'équipe Data
KID_TRANSACTION_COLUMNS = ("Explicit_Transaction_costs_ex_ante_3_years_mean", "Implicit_trans_costs_ex_ante3Y_mean")
PRODUCT, SHARE, REGISTRATION = "pi_out_product_active", "PI_OUT_Share", "PI_OUT_CountryOfRegistration"


NUMBER_WORDS = {"un": 1, "une": 1, "one": 1, "deux": 2, "two": 2, "trois": 3, "three": 3, "quatre": 4, "four": 4, "cinq": 5,
                "five": 5, "dix": 10, "ten": 10}
THRESHOLD = re.compile(r"(?:plus d'?|plus de|more than|over|>=?|superieur a|superieure a|au moins|at least|minimum de|min\.?)\s*"
                       r"(\d+(?:[.,]\d+)?|" + "|".join(NUMBER_WORDS) + r")\s*(?:an|ans|annee|annees|year|years|yr)\b")


def years_threshold(text: str) -> float | None:
    from .ontology import norm  # « > 3 ans » : le comparateur est gardé avant normalisation

    m = THRESHOLD.search(norm(str(text).replace("≥", " au moins ").replace(">", " plus de ")))
    if not m:
        return None
    raw = m.group(1)
    return float(NUMBER_WORDS.get(raw, raw.replace(",", ".") if raw not in NUMBER_WORDS else 0))


@dataclass
class Raw:
    value: Any
    evidence: str  # d'où vient la valeur (lisible)
    data_date: date | None = None  # date de la donnée, si connue
    note: str = ""  # précision ou raison d'absence
    stale: bool = False
    ambiguous_period: bool = False


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and not math.isfinite(value)) else float(value)
    try:
        return float(str(value).replace(" ", "").replace(",", ".").replace("%", ""))
    except ValueError:
        return None


def to_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            continue
    return None


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


class Values:
    def __init__(self, data: DataAccess, ontology: Ontology, pid: str | None, isin: str | None, as_of: date):
        self.data, self.ontology, self.pid, self.isin, self.as_of = data, ontology, pid, isin, as_of
        self.errors: list[str] = []
        self._product: dict[str, Any] | None = None
        self._share: dict[str, Any] | None = None
        self._loaded = False
        self._cache: dict[str, Any] = {}

    # ------------------------------------------------------------------ Product Info
    def _columns(self, table: str) -> list[str]:
        cols = {c for concept in self.ontology.usable() for t, c in concept.columns if t == table}
        cols |= {concept.asof.split(".", 1)[1] for concept in self.ontology.usable() if concept.asof and concept.asof.startswith(table + ".")}
        if table == SHARE:
            cols |= {"pi_shareid", "ProductID", "ISIN_Code", "Subscription_Currency", "First_NAV_Date", "Swing_Pricing", "ADL"}
        if table == PRODUCT:
            cols |= set(LABEL_COLUMNS) | set(KID_TRANSACTION_COLUMNS) | {"First_NAV_Date", "Creation_Date", "Start_date_Portfolio_manager"}
        return sorted(cols)

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self.pid:
            cols = ", ".join(f"p.{c}" for c in self._columns(PRODUCT))
            try:
                frame = self.data.query(f"SELECT {cols} FROM dbo.{PRODUCT} p WHERE p.pi_productid = :pid", {"pid": self.pid})
                if len(frame) > 1:
                    self.errors.append(f"Plusieurs fiches Product Info pour le fonds {self.pid} : réponses « fonds » suspendues.")
                elif len(frame) == 1:
                    self._product = frame.iloc[0].to_dict()
            except DataError as error:
                self.errors.append(f"Product Info (fonds) : {error} {error.hint}")
        if self.isin:
            cols = ", ".join(f"s.{c}" for c in self._columns(SHARE))
            try:
                frame = self.data.query(f"SELECT {cols} FROM dbo.{SHARE} s WHERE s.ISIN_Code = :isin", {"isin": self.isin})
                if self.pid and len(frame) > 1:
                    frame = frame[frame["ProductID"].astype(str) == str(self.pid)] if (frame["ProductID"].astype(str) == str(self.pid)).any() else frame
                if len(frame) > 1:
                    # Doublons identiques : sans conséquence ; doublons contradictoires : on s'abstient.
                    if len(frame.drop_duplicates()) == 1:
                        frame = frame.iloc[:1]
                    else:
                        self.errors.append(f"Plusieurs fiches Product Info contradictoires pour l'ISIN {self.isin} : réponses « part » suspendues.")
                        frame = frame.iloc[:0]
                if len(frame) == 1:
                    self._share = frame.iloc[0].to_dict()
                    if self.pid and str(self._share.get("ProductID") or "") not in ("", str(self.pid)):
                        self.errors.append(f"L'ISIN {self.isin} n'est pas rattaché au fonds choisi dans Product Info : vérifiez la part.")
            except DataError as error:
                self.errors.append(f"Product Info (part) : {error} {error.hint}")

    @property
    def share_id(self) -> str | None:
        self.load()
        return str(self._share["pi_shareid"]) if self._share and not is_empty(self._share.get("pi_shareid")) else None

    def _pi(self, concept: Concept, lang: str) -> Raw:
        self.load()
        table, column = concept.source_for(lang).split(".", 1)
        row = self._product if table == PRODUCT else self._share
        if row is None:
            who = "fonds" if table == PRODUCT else "part"
            return Raw(None, f"{table}.{column}", note=f"fiche Product Info de la {who} introuvable" if who == "part" else "fiche Product Info du fonds introuvable")
        value = row.get(column)
        data_date = None
        if concept.asof:
            data_date = to_date(row.get(concept.asof.split(".", 1)[1]))
        transform = concept.transform
        if transform == "not_null":
            d = to_date(value)
            value = "yes" if (d is not None and d <= self.as_of) else ("no" if d is None else "no")
        elif transform == "present":
            # renseigné → oui ; vide → inconnu (jamais « non » : vide, non et non applicable sont des états différents)
            value = None if is_empty(value) else "yes"
        elif transform == "negate":
            v = self.ontology.vocab_value("yes_no", value)
            value = None if v is None else ("no" if v.id == "yes" else "yes")
        elif isinstance(transform, dict) and "in" in transform:
            base = self.ontology.vocab_value("regulation", value)
            value = None if base is None else ("yes" if base.id in transform["in"] else "no")
        if concept.type == "amount" and table == SHARE and not is_empty(value) and not is_empty(row.get("Subscription_Currency")):
            value = (value, str(row.get("Subscription_Currency")).strip())  # montant exprimé dans la devise de la part
        return Raw(value, f"Product Info · {table}.{column}", data_date=data_date)

    # ------------------------------------------------------------------ JUMP
    def _jump(self, name: str, as_of: date | None = None) -> pd.DataFrame | None:
        as_of = as_of or self.as_of
        key = f"{name}@{as_of.isoformat()}"
        if key in self._cache:
            return self._cache[key]
        sid = self.share_id
        jf, jp = self._jump_ids()
        # Clés robustes : identifiants JUMP retrouvés par l'ISIN (référence des questionnaires), puis identifiants PI.
        part_filter = "(a.ID_JUMP_PART = :jp OR UPPER(LTRIM(RTRIM(a.CODE_ISIN_PART))) = :isin OR a.ID_PI_PART = :sid)"
        fund_a = "(a.ID_JUMP_FONDS = :jf OR a.ID_PI_FONDS = :pid)"
        fund_b = "(b.ID_JUMP_FONDS = :jf OR b.ID_PI_FONDS = :pid)"
        fund_h = "(h.ID_JUMP_FONDS = :jf OR h.ID_PI_FONDS = :pid)"
        fund_i = "(i.ID_JUMP_FONDS = :jf OR i.ID_PI_FONDS = :pid)"
        queries = {
            "fund_aum": f"""SELECT TOP 1 a.ACTIF_NET_TOTAL_EURO, a.ACTIF_NET_TOTAL_DEVISE_FONDS, a.DEVISE_FONDS, a.DATE_VL
                FROM dbo.JUMP_portfolio_aum a WHERE {fund_a} AND a.DATE_VL <= :as_of ORDER BY a.DATE_VL DESC""",
            "share_aum": f"""SELECT TOP 1 a.ACTIF_NET_DEVISE_PART, a.ACTIF_NET_PART_EURO, a.VL_UNITAIRE, a.NOMBRE_PARTS, a.DEVISE_VL, a.DATE_VL
                FROM dbo.JUMP_portfolio_aum a WHERE {part_filter} AND a.DATE_VL <= :as_of ORDER BY a.DATE_VL DESC""",
            "share_classes": f"""SELECT COUNT(DISTINCT a.CODE_ISIN_PART) AS valeur FROM dbo.JUMP_portfolio_aum a
                WHERE {fund_a} AND a.DATE_VL = (SELECT MAX(b.DATE_VL) FROM dbo.JUMP_portfolio_aum b
                WHERE {fund_b} AND b.DATE_VL <= :as_of)""",
            "holdings": f"""SELECT h.NOM_INSTRUMENT, h.CLASSE_ACTIF, h.DEVISE_INSTRUMENT, h.TYPE_HOLDING, h.POIDS_LIGNE_EXPO, h.DATE_INVENTAIRE
                FROM dbo.JUMP_portfolio_holdings h WHERE {fund_h} AND h.DATE_INVENTAIRE = (
                SELECT MAX(i.DATE_INVENTAIRE) FROM dbo.JUMP_portfolio_holdings i WHERE {fund_i} AND i.DATE_INVENTAIRE <= :as_of)""",
            "nav": f"""SELECT a.DATE_VL, a.VL_UNITAIRE, a.DIVIDEND_AMOUNT, a.COEFFICIENT_OST, a.VL_BENCH, a.NOM_BENCH
                FROM dbo.JUMP_portfolio_aum a WHERE {part_filter} AND a.DATE_VL <= :as_of ORDER BY a.DATE_VL""",
        }
        needs_fund = name in {"fund_aum", "share_classes", "holdings"}
        if (needs_fund and not (self.pid or jf)) or (not needs_fund and not (sid or self.isin or jp)):
            self._cache[key] = None
            return None
        params = {"pid": self.pid or "", "isin": (self.isin or "").strip().upper(), "sid": sid or "", "jf": jf or "", "jp": jp or "",
                  "as_of": as_of.isoformat()}
        try:
            frame = self.data.query(queries[name], params)
        except DataError as error:
            self.errors.append(f"JUMP ({name}) : {error}")
            frame = None
        self._cache[key] = frame
        return frame

    def _jump_ids(self) -> tuple[str | None, str | None]:
        """(ID_JUMP_FONDS, ID_JUMP_PART) de la part choisie, retrouvés par l'ISIN, sinon par les identifiants PI."""
        if "jump_ids" in self._cache:
            return self._cache["jump_ids"]
        sid = self.share_id
        ids: tuple[str | None, str | None] = (None, None)
        try:
            frame = self.data.query(
                """SELECT TOP 1 a.ID_JUMP_FONDS, a.ID_JUMP_PART FROM dbo.JUMP_portfolio_aum a
                WHERE UPPER(LTRIM(RTRIM(a.CODE_ISIN_PART))) = :isin OR a.ID_PI_PART = :sid OR a.ID_PI_FONDS = :pid
                ORDER BY CASE WHEN UPPER(LTRIM(RTRIM(a.CODE_ISIN_PART))) = :isin THEN 0 ELSE 1 END, a.DATE_VL DESC""",
                {"isin": (self.isin or "").strip().upper(), "sid": sid or "", "pid": self.pid or ""})
            if len(frame):
                row = frame.iloc[0]
                ids = (None if is_empty(row["ID_JUMP_FONDS"]) else str(row["ID_JUMP_FONDS"]),
                       None if is_empty(row["ID_JUMP_PART"]) else str(row["ID_JUMP_PART"]))
            else:
                self.errors.append(f"JUMP : aucune ligne pour l'ISIN {self.isin or '—'} ni le fonds {self.pid or '—'} "
                                   "(JUMP_portfolio_aum) : encours, VL, performances et inventaire indisponibles.")
        except DataError as error:
            self.errors.append(f"JUMP (identifiants) : {error}")
        self._cache["jump_ids"] = ids
        return ids

    def date_for(self, u: Understanding) -> date:
        """Date de la mesure : la date citée dans la question si elle précède la date d'arrêté, sinon la date d'arrêté."""
        if u.explicit_date and u.explicit_date <= self.as_of:
            return u.explicit_date
        return self.as_of

    def _registrations(self) -> list[str] | None:
        if "registrations" in self._cache:
            return self._cache["registrations"]
        sid = self.share_id
        out = None
        if sid:
            try:
                frame = self.data.query(f"SELECT r.Country FROM dbo.{REGISTRATION} r WHERE r.pi_shareid = :sid", {"sid": sid})
                out = sorted({str(c).strip() for c in frame["Country"] if not is_empty(c)})
            except DataError as error:
                self.errors.append(f"Pays d'enregistrement : {error}")
        self._cache["registrations"] = out
        return out

    def _nav(self) -> pd.DataFrame:
        if "nav_frame" not in self._cache:
            self._cache["nav_frame"] = P.nav_frame(self._jump("nav"))
        return self._cache["nav_frame"]

    def _computed(self, concept: Concept, u: Understanding) -> Raw:
        kind, measure = concept.source.split(":", 1)
        if kind == "registration":
            countries = self._registrations()
            if countries is None:
                return Raw(None, "Product Info · PI_OUT_CountryOfRegistration", note="part introuvable dans Product Info")
            if measure == "countries":
                return Raw(countries, "Product Info · PI_OUT_CountryOfRegistration.Country")
            if not u.countries:
                return Raw(None, "Product Info · PI_OUT_CountryOfRegistration.Country", note="aucun pays reconnu dans la question")
            ids = {(self.ontology.vocab_value("country", c).id if self.ontology.vocab_value("country", c) else c) for c in countries}
            return Raw("yes" if all(c in ids for c in u.countries) else "no", "Product Info · PI_OUT_CountryOfRegistration.Country")
        if kind == "fund":
            if measure in {"track_record", "pm_tenure"}:
                return self._seniority(measure, u)
            return self._fund_measure(measure)
        if kind == "share" and measure == "anti_dilution":
            return self._anti_dilution()
        if kind == "precedent":
            return Raw(None, "anciens RFI", note="réponse de niveau société : tirée des anciens RFI, pas de Fabric")
        if kind == "meta":
            if measure == "today":
                return Raw(date.today(), "date du jour (rédaction)")
            return Raw(self.as_of, "date d'arrêté choisie pour ce RFI", data_date=self.as_of)
        if kind == "jump":
            return self._jump_measure(measure, u)
        return self._perf_measure(measure, u)

    def _seniority(self, measure: str, u: Understanding) -> Raw:
        """« Track record de plus d'1 an ? », « Ancienneté du gérant > 3 ans » : comparaison d'une date Product Info au seuil cité."""
        years = years_threshold(u.text)
        if years is None:
            return Raw(None, measure, note="seuil (nombre d'années) non lu dans la question")
        self.load()
        if measure == "track_record":
            candidates = [(self._share, SHARE, "First_NAV_Date"), (self._product, PRODUCT, "First_NAV_Date"), (self._product, PRODUCT, "Creation_Date")]
        else:
            candidates = [(self._product, PRODUCT, "Start_date_Portfolio_manager")]
        for row, table, column in candidates:
            d = to_date(row.get(column)) if row else None
            if d is not None:
                try:
                    limit = self.as_of.replace(year=self.as_of.year - int(years))
                except ValueError:  # 29 février
                    limit = self.as_of.replace(year=self.as_of.year - int(years), day=28)
                return Raw("yes" if d <= limit else "no", f"Product Info · {table}.{column} = {d.strftime('%d/%m/%Y')} (seuil {years:g} an(s))",
                           data_date=d)
        return Raw(None, measure, note="date de départ absente de Product Info")

    def _anti_dilution(self) -> Raw:
        """Mécanisme anti-dilution = swing pricing OU anti-dilution levy (oui si l'un est en place, non si les deux sont absents)."""
        self.load()
        if self._share is None:
            return Raw(None, SHARE, note="part introuvable dans Product Info")
        flags = [self.ontology.vocab_value("yes_no", self._share.get(c)) for c in ("Swing_Pricing", "ADL")]
        evidence = f"Product Info · {SHARE}.Swing_Pricing / {SHARE}.ADL"
        if any(f is not None and f.id == "yes" for f in flags):
            return Raw("yes", evidence)
        if all(f is not None and f.id == "no" for f in flags):
            return Raw("no", evidence)
        return Raw(None, evidence, note="swing pricing ou ADL non renseigné")

    def _fund_measure(self, measure: str) -> Raw:
        self.load()
        row = self._product
        if row is None:
            return Raw(None, PRODUCT, note="fiche Product Info du fonds introuvable")
        if measure in {"labels", "labelled"}:
            held = []
            for column, name in LABEL_COLUMNS.items():
                v = self.ontology.vocab_value("yes_no", row.get(column))
                raw = row.get(column)
                if (v is not None and v.id == "yes") or (v is None and not is_empty(raw) and str(raw).strip().lower() not in {"0", "false", "non", "no"}):
                    held.append(name)
            evidence = "Product Info · " + ", ".join(f"{PRODUCT}.{c}" for c in LABEL_COLUMNS)
            if not held:
                return Raw(None, evidence, note="aucun label dans Product Info (ISR, Towards, Finansol) : un autre label reste possible")
            return Raw("yes" if measure == "labelled" else ", ".join(held), evidence)
        if measure == "transaction_costs_kid":
            parts = [_num(row.get(c)) for c in KID_TRANSACTION_COLUMNS]
            if any(p is None for p in parts):
                return Raw(None, "Product Info · coûts de transaction ex ante", note="coût explicite ou implicite manquant")
            return Raw(round(sum(parts), 4), "Product Info · " + " + ".join(f"{PRODUCT}.{c}" for c in KID_TRANSACTION_COLUMNS))
        return Raw(None, measure, note="mesure inconnue")

    def _jump_measure(self, measure: str, u: Understanding) -> Raw:
        at = self.date_for(u)
        if measure in {"fund_aum", "fund_aum_date"}:
            f = self._jump("fund_aum", at)
            if f is None or f.empty:
                return Raw(None, "JUMP · JUMP_portfolio_aum", note="aucun encours JUMP pour ce fonds à cette date")
            row = f.iloc[0]
            d = to_date(row["DATE_VL"])
            if measure == "fund_aum_date":
                return Raw(d, "JUMP · JUMP_portfolio_aum.DATE_VL", data_date=d)
            if u.currency == "EUR" or not u.currency:
                value, ccy, col = row["ACTIF_NET_TOTAL_EURO"], "EUR", "ACTIF_NET_TOTAL_EURO"
                if not u.currency and str(row["DEVISE_FONDS"] or "EUR") != "EUR":
                    value, ccy, col = row["ACTIF_NET_TOTAL_DEVISE_FONDS"], str(row["DEVISE_FONDS"]), "ACTIF_NET_TOTAL_DEVISE_FONDS"
            elif u.currency == str(row["DEVISE_FONDS"]):
                value, ccy, col = row["ACTIF_NET_TOTAL_DEVISE_FONDS"], u.currency, "ACTIF_NET_TOTAL_DEVISE_FONDS"
            else:
                return Raw(None, "JUMP · JUMP_portfolio_aum", note=f"encours non disponible en {u.currency}")
            return Raw((_num(value), ccy), f"JUMP · JUMP_portfolio_aum.{col}", data_date=d, stale=self._stale(d, ref=at))
        if measure in {"share_aum", "nav", "shares_outstanding"}:
            f = self._jump("share_aum", at)
            if f is None or f.empty:
                return Raw(None, "JUMP · JUMP_portfolio_aum", note="aucune VL JUMP pour cette part à cette date")
            row = f.iloc[0]
            d = to_date(row["DATE_VL"])
            if measure == "nav":
                return Raw((_num(row["VL_UNITAIRE"]), str(row["DEVISE_VL"] or "")), "JUMP · JUMP_portfolio_aum.VL_UNITAIRE", data_date=d, stale=self._stale(d, ref=at))
            if measure == "shares_outstanding":
                return Raw(_num(row["NOMBRE_PARTS"]), "JUMP · JUMP_portfolio_aum.NOMBRE_PARTS", data_date=d, stale=self._stale(d, ref=at))
            if u.currency == "EUR":
                return Raw((_num(row["ACTIF_NET_PART_EURO"]), "EUR"), "JUMP · JUMP_portfolio_aum.ACTIF_NET_PART_EURO", data_date=d, stale=self._stale(d, ref=at))
            if u.currency and u.currency != str(row["DEVISE_VL"]):
                return Raw(None, "JUMP · JUMP_portfolio_aum", note=f"encours de la part non disponible en {u.currency}")
            return Raw((_num(row["ACTIF_NET_DEVISE_PART"]), str(row["DEVISE_VL"] or "")), "JUMP · JUMP_portfolio_aum.ACTIF_NET_DEVISE_PART", data_date=d, stale=self._stale(d, ref=at))
        if measure == "share_classes":
            f = self._jump("share_classes", at)
            if f is None or f.empty:
                return Raw(None, "JUMP · JUMP_portfolio_aum", note="aucune part JUMP")
            return Raw(_num(f.iloc[0]["valeur"]), "JUMP · nombre d'ISIN distincts à la dernière VL")
        holdings = self._jump("holdings", at)
        if holdings is None or holdings.empty:
            return Raw(None, "JUMP · JUMP_portfolio_holdings", note="aucun inventaire JUMP pour ce fonds à cette date")
        d = to_date(holdings["DATE_INVENTAIRE"].iloc[0])
        frame = holdings.copy()
        weights = frame["POIDS_LIGNE_EXPO"].map(_num).fillna(0.0)
        # Unité de POIDS_LIGNE_EXPO À CONFIRMER : fraction si la somme est proche de 1, sinon points de %.
        frame["poids"] = weights * 100 if 0 < weights.abs().sum() <= 1.5 else weights
        securities = frame[frame["TYPE_HOLDING"].fillna("").astype(str).str.upper() != "CASH"]
        evidence = f"JUMP · JUMP_portfolio_holdings (inventaire du {d.strftime('%d/%m/%Y') if d else '?'})"
        if measure == "holdings_count":
            return Raw(int(len(securities)), evidence, data_date=d, stale=self._stale(d, 40, ref=at))
        top = securities.sort_values("poids", ascending=False).head(10)
        if measure == "top10_weight":
            return Raw(round(float(top["poids"].sum()), 2), evidence, data_date=d, stale=self._stale(d, 40, ref=at))
        if measure in {"position_name", "position_weight"}:
            if not u.rank or u.rank > len(securities):
                return Raw(None, evidence, note="rang de la position non lu dans la question")
            row = securities.sort_values("poids", ascending=False).iloc[u.rank - 1]
            value = str(row["NOM_INSTRUMENT"]) if measure == "position_name" else round(float(row["poids"]), 2)
            return Raw(value, f"{evidence} · rang {u.rank}", data_date=d, stale=self._stale(d, 40, ref=at))
        if measure == "top10_list":
            return Raw([(str(r.NOM_INSTRUMENT), float(r.poids)) for r in top.itertuples()], evidence, data_date=d, stale=self._stale(d, 40, ref=at))
        column = {"allocation_asset": "CLASSE_ACTIF", "allocation_currency": "DEVISE_INSTRUMENT"}[measure]
        grouped = frame.groupby(frame[column].fillna("Autres"))["poids"].sum().sort_values(ascending=False)
        return Raw([(str(k), float(v)) for k, v in grouped.items() if abs(v) >= 0.05], evidence, data_date=d, stale=self._stale(d, 40, ref=at))

    def _perf_measure(self, measure: str, u: Understanding) -> Raw:
        nav = self._nav()
        if nav.empty:
            return Raw(None, "JUMP · VL de la part", note="aucune VL JUMP pour cette part")
        index = P.adjusted_index(nav)
        at = self.date_for(u)
        evidence = "JUMP · VL de la part, dividendes réinvestis (méthode App4everyone)"
        if measure in {"return", "bench_return"}:
            period = u.period
            if period is None:
                return Raw(None, evidence, note="période non précisée dans la question")
            series = index if measure == "return" else P.benchmark_index(nav)
            if measure == "bench_return":
                evidence = "JUMP · VL_BENCH (niveau de l'indicateur de référence)"
                if series.notna().sum() < 2:
                    return Raw(None, evidence, note="pas de niveau d'indice dans JUMP")
            ambiguous = period.annualized is None and ((period.kind == "years" and period.n > 1) or period.kind == "inception")
            annualize = bool(period.annualized)
            res = P.period_return(series, period, at, annualize)
            label = period.label() + ("" if not ambiguous else " (cumulée : précisez si annualisée)")
            return Raw(res.value, f"{evidence} · {label}", data_date=res.end, note=res.note, stale=res.stale, ambiguous_period=ambiguous)
        years = 1.0
        ambiguous = True
        if u.period and u.period.kind == "years":
            years, ambiguous = float(u.period.n), False
        elif u.period and u.period.kind == "months":
            years, ambiguous = u.period.n / 12, False
        if measure == "volatility":
            res = P.volatility(index, at, years)
        elif measure == "max_drawdown":
            res = P.max_drawdown(index, at, years)
        else:
            bench = P.benchmark_index(nav)
            if bench.notna().sum() < 20:
                return Raw(None, evidence, note="pas de niveau d'indice dans JUMP")
            res = P.tracking_error(index, bench, at, years)
        label = f"{evidence} · {years:g} an(s)" + (" (période par défaut)" if ambiguous else "")
        return Raw(res.value, label, data_date=res.end, note=res.note, stale=res.stale, ambiguous_period=ambiguous)

    def _stale(self, d: date | None, days: int = P.STALE_DAYS, ref: date | None = None) -> bool:
        return d is not None and ((ref or self.as_of) - d).days > days

    # ------------------------------------------------------------------ point d'entrée
    def get(self, concept: Concept, u: Understanding, lang: str) -> Raw:
        if concept.problems:
            return Raw(None, concept.id, note="; ".join(concept.problems))
        if concept.scope == "share" and not self.isin:
            return Raw(None, concept.id, note="aucune part choisie")
        if concept.scope == "fund" and not self.pid and not concept.computed:
            return Raw(None, concept.id, note="aucun fonds choisi")
        if concept.computed:
            return self._computed(concept, u)
        return self._pi(concept, lang)


__all__ = ["Values", "Raw", "to_date", "is_empty", "PRODUCT", "SHARE"]
