"""Lakehouse de démonstration.

Données 100 % fictives, générées de façon déterministe, avec exactement les tables et
colonnes du catalogue. Les ISIN commencent par « QZ » (aucun pays n'utilise ce préfixe)
et les fonds portent des noms de légende arthurienne : aucun risque de confusion.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .catalog import Catalog

MOCK_VERSION = "4"

FUNDS = [
    ("Avalon Actions Europe", "EUR", "Actions", "Indice Fictif Actions Europe NR"),
    ("Brocéliande Crédit Haut Rendement", "EUR", "Obligations", "Indice Fictif HY Euro"),
    ("Camelot Multi-Actifs Patrimoine", "EUR", "Multi-actifs", "Composite Fictif 50/50"),
    ("Excalibur Actions Monde", "USD", "Actions", "Indice Fictif Actions Monde NR"),
    ("Graal Convertibles Europe", "EUR", "Convertibles", "Indice Fictif Convertibles Europe"),
    ("Viviane Monétaire", "EUR", "Monétaire", "Taux Fictif au Jour le Jour"),
    ("Morgane Petites Capitalisations", "EUR", "Actions", "Indice Fictif Small Caps Europe"),
    ("Lancelot Obligations Vertes", "EUR", "Obligations", "Indice Fictif Green Bonds"),
    ("Perceval Dette Émergente", "USD", "Obligations", "Indice Fictif Dette Émergente"),
    ("Tintagel Échéance 2029", "EUR", "Obligations", ""),
    ("Galaad Actions Amérique", "USD", "Actions", "Indice Fictif Actions US"),
    ("Merlin Obligations Court Terme", "EUR", "Obligations", "Indice Fictif Euro Agg 1-3"),
]

SHARE_CLASSES = [("C EUR", "EUR", 1.0), ("I EUR", "EUR", 1.0), ("R USD H", "USD", 1.0)]

EQUITY_NAMES = [
    "Chaudronnerie Imaginaire", "Lumières du Lac", "Forges de l'Enchanteur", "Pierres Levées",
    "Compagnie des Brumes", "Ateliers du Dragon", "Banque de la Table Ronde", "Énergies Sylvestres",
    "Parchemins Numériques", "Alchimie Industrielle", "Transports de la Licorne", "Télécoms du Château",
    "Vergers d'Avalon", "Cristaux & Associés", "Assurances du Heaume", "Navires de Cornouailles",
    "Pharmacie des Fées", "Semi-conducteurs Runiques", "Hôtellerie du Graal", "Mines de Mithril",
    "Logiciels Sortilège", "Brasseries du Barde", "Ciments du Donjon", "Robotique Golem",
]
EQUITY_SUFFIX = ["SA", "SE", "plc", "AG", "Inc", "NV"]
BOND_ISSUERS = ["République Fictive", "Royaume d'Avalon", "Duché de Brocéliande", "Ville de Camelot",
                "Crédit du Lac", "Forges de l'Enchanteur", "Énergies Sylvestres", "Télécoms du Château"]
CURRENCIES = ["EUR", "EUR", "EUR", "USD", "USD", "GBP", "CHF", "JPY"]
FX_TO_EUR = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "CHF": 1.04, "JPY": 0.0062}

_ISIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def isin_check_digit(body: str) -> str:
    """Chiffre de contrôle ISIN (Luhn sur la conversion lettres → nombres)."""
    digits = "".join(str(int(ch, 36)) for ch in body)
    total = 0
    for index, ch in enumerate(reversed(digits)):
        n = int(ch)
        if index % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def fake_isin(rng: random.Random) -> str:
    body = "QZ" + "".join(rng.choice(_ISIN_ALPHABET) for _ in range(9))
    return body + isin_check_digit(body)


def business_days(start: date, end: date) -> list[date]:
    days, current = [], start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def month_ends(start: date, end: date) -> list[date]:
    result = []
    current = date(start.year, start.month, 1)
    while current <= end:
        nxt = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
        last = nxt - timedelta(days=1)
        while last.weekday() >= 5:
            last -= timedelta(days=1)
        if last <= end:
            result.append(last)
        current = nxt
    return result


# ------------------------------------------------------------------ Product Info (fictif)
DEPOSITARIES = ["Banque du Lac", "Dépositaire d'Avalon", "Caisse de Camelot"]
AUDITORS = ["Cabinet Merlin & Associés", "Audit de la Table Ronde"]
MANAGERS = ["Viviane Lac", "Arthur Pendragon", "Morgane Fay", "Perceval Galles", "Guenièvre Camel", "Lancelot Dulac"]
STYLE_INFO = {
    "Actions": ("Actions", "Europe", "5", "Article 8", 5),
    "Obligations": ("Obligations", "Zone euro", "3", "Article 8", 3),
    "Multi-actifs": ("Diversifié", "Monde", "4", "Article 8", 4),
    "Convertibles": ("Convertibles", "Europe", "4", "Article 6", 4),
    "Monétaire": ("Monétaire", "Zone euro", "1", "Article 8", 0.25),
}


def _pi_product(i: int, name: str, ccy: str, style: str, bench: str, pi_id: str, fund_id: str, start: date) -> dict:
    r = random.Random(1000 + i)
    asset, zone, sri, sfdr, horizon = STYLE_INFO[style]
    created = date(r.randint(1998, 2021), r.randint(1, 12), 1)
    return {
        "Id": f"guid-{pi_id}", "pi_productid": pi_id, "Product_Global_ID": f"PG{4000 + i}", "Product_Name": name,
        "statecodename": "Active", "Legal_Form": r.choice(["FCP", "SICAV", "Compartiment de SICAV"]),
        "Domiciliation": r.choice(["France", "France", "Luxembourg"]), "Umbrella_Name": "Fictive SICAV" if i % 3 == 0 else None,
        "Creation_Date": created.isoformat() + " 00:00:00", "First_NAV_Date": created.isoformat() + " 00:00:00",
        "ESG_SFDR_Article": sfdr, "Official_Risk_Scale": sri, "Official_Risk_Scale_SRRI": sri,
        "AMF_Classification": {"Actions": "Actions des pays de l'UE", "Obligations": "Obligations euro"}.get(asset),
        "Asset_Class": asset, "Investment_Zone": zone, "Accounting_Currency": ccy,
        "Benchmark_Name": bench or None, "Benchmark_Currency": ccy if bench else None,
        "Portfolio_Manager": MANAGERS[i % len(MANAGERS)], "Portfolio_Manager_backup_1": MANAGERS[(i + 2) % len(MANAGERS)],
        "Start_date_Portfolio_manager": date(r.randint(2012, 2022), 1, 1).isoformat() + " 00:00:00",
        "Depositary": r.choice(DEPOSITARIES), "Custodian": r.choice(DEPOSITARIES), "Fund_Administrator": "Administrateur Fictif",
        "Commissaire_Aux_Comptes": r.choice(AUDITORS), "Transfer_Agent": "Agent de Transfert Fictif",
        "Centralizing_Agent": "Centralisateur Fictif", "LEI_Code": f"QZ00{r.randint(10**15, 10**16 - 1)}",
        "Recommended_Investment_Period": f"{horizon} ans" if horizon >= 1 else "3 mois",
        "NAV_Frequency": "Quotidienne", "NAV_Calculation_Day": "Chaque jour ouvré",
        "Max_management_fee_PerCent": round(r.choice([0.5, 0.8, 1.2, 1.6, 2.0]), 2),
        "Performance_fees": r.choice(["Oui", "Non", "Non"]), "High_Water_Mark": "Oui",
        "Applicable_UCI_Regulation": "OPCVM", "Fund_Range": style, "Management_Expertise_Level_1": style,
        "Gips_Compliance": "Oui", "ESG_AMF_Category": "Catégorie 2" if sfdr == "Article 8" else "Catégorie 3",
        "Investment_objective_FR": f"Surperformer {bench or 'son objectif de gestion'} sur {horizon} ans (texte fictif).",
        "Investment_objective_EN": f"Outperform {bench or 'its management objective'} over {horizon} years (fictitious).",
        "AIM_Portfolio_Code": f"AIM{i:03d}", "Fund_Administrator_Portfolio_Code": fund_id,
    }


def _pi_share(i: int, k: int, part: dict, pi_id: str, start: date) -> dict:
    r = random.Random(2000 + i * 10 + k)
    institutional = part["name"].endswith(" I EUR")
    created = date(r.randint(2005, 2022), r.randint(1, 12), 1)
    fee = round(r.choice([0.4, 0.6, 0.8]) if institutional else r.choice([1.0, 1.5, 1.8]), 2)
    return {
        "Id": f"guid-{part['pi']}", "pi_shareid": part["pi"], "ProductID": pi_id, "ISIN_Code": part["isin"],
        "Share_Name": part["name"], "Share_Class": part["name"].rsplit(" ", 2)[-2], "Subscription_Currency": part["ccy"],
        "Creation_Date": created.isoformat() + " 00:00:00", "First_NAV_Date": created.isoformat() + " 00:00:00",
        "Initial_NAV": 1000.0 if institutional else 100.0,
        "Initial_Subscription_Minimum_Amount": 500000.0 if institutional else 1.0,
        "Max_Financial_Management_Fees": round(fee + 0.2, 2), "Actual_Financial_Management_Fees": fee,
        "Ongoing_Charges_ex_post": round(fee + r.uniform(0.05, 0.3), 2), "Ongoing_Charges_ex_ante": round(fee + 0.2, 2),
        "Maximum_Subscription_Fee_Rate_Not_Retained": 0.0 if institutional else 3.0, "Maximum_Redemption_Fee_Rate_Not_Retained": 0.0,
        "Subscription_cut_off_time": "12:00", "Redemption_cut_off_time": "12:00", "Subscription_Settlement_Date": "J+2",
        "Redemption_Settlement_Date": "J+2", "Income_Distribution": r.choice(["Capitalisation", "Distribution"]),
        "Bloomberg_Ticker": f"{part['isin'][2:8]} QZ", "Morningstar_rating": r.randint(2, 5),
        "Investor_Type": "Institutionnel" if institutional else "Tous souscripteurs",
        "Share_Hedged_Against_FX_Exposure": "Oui" if part["name"].endswith(" H") else "Non",
        "Main_Share": "Oui" if k == 0 else "Non", "Performance_fees": "Non", "Product_Status": "Active",
    }


def _sqlite_type(kind: str) -> str:
    return {"number": "REAL", "date": "TEXT", "datetime": "TEXT"}.get(kind, "TEXT")


def build_mock_lakehouse(catalog: Catalog, path: Path, today: date | None = None) -> Path:
    """Crée (ou recrée si obsolète) la base SQLite de démonstration."""
    today = today or date.today()
    stamp = f"{MOCK_VERSION}:{today.isoformat()}"
    if path.exists():
        try:
            with sqlite3.connect(path) as conn:
                row = conn.execute("SELECT value FROM _merlin_meta WHERE key='stamp'").fetchone()
            if row and row[0] == stamp:
                return path
        except sqlite3.Error:
            pass
        path.unlink()

    rng = random.Random(42)
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    for table in catalog.tables.values():
        cols = ", ".join(f'"{c.name}" {_sqlite_type(c.kind)}' for c in table.columns)
        conn.execute(f'CREATE TABLE "{table.name}" ({cols})')

    start = date(today.year - 1, today.month, 1)
    load_ts = datetime.combine(today, datetime.min.time()).replace(hour=6, minute=12).isoformat(" ")

    # ---------------------------------------------------------- instruments
    instruments = []
    for i in range(140):
        is_bond = i % 3 == 0
        currency = rng.choice(CURRENCIES)
        if is_bond:
            issuer = rng.choice(BOND_ISSUERS)
            coupon = rng.choice([0.5, 1.25, 2.0, 2.75, 3.5, 4.25, 5.0])
            name = f"{issuer} {coupon:.2f}% {rng.randint(2026, 2036)}"
            asset_class, type_code, debt = "Obligations", "OBL", rng.choice(["Senior", "Senior", "Subordonnée", "Souveraine"])
        else:
            name = f"{rng.choice(EQUITY_NAMES)} {rng.choice(EQUITY_SUFFIX)}"
            asset_class, type_code, debt = "Actions", "ACT", None
        isin = fake_isin(rng)
        instruments.append({
            "id": f"INS{10000 + i}", "isin": isin, "bbg": f"{isin[2:6]} QZ {'Corp' if is_bond else 'Equity'}",
            "name": name, "currency": currency, "type": type_code, "class": asset_class,
            "debt": debt, "price": round(rng.uniform(20, 400) if not is_bond else rng.uniform(85, 108), 4),
            "is_bond": is_bond,
        })

    # ---------------------------------------------------------- funds & parts
    aum_rows, holdings_rows = [], []
    pi_products: list[dict] = []
    pi_shares: list[dict] = []
    nav_days = business_days(start, today - timedelta(days=1))
    inventory_days = month_ends(start, today - timedelta(days=1))

    for f_index, (fund_name, fund_ccy, style, bench) in enumerate(FUNDS):
        fund_id, pi_id = f"F{1000 + f_index}", f"PI-{700 + f_index}"
        aim_code = f"AIM{f_index:03d}"
        total_eur = rng.uniform(80e6, 2.4e9)
        n_parts = rng.choice([1, 2, 3])
        parts = []
        for p_index in range(n_parts):
            label, ccy, _ = SHARE_CLASSES[p_index]
            parts.append({
                "id": f"{fund_id}-P{p_index + 1}", "pi": f"{pi_id}-{p_index + 1}",
                "isin": fake_isin(rng), "name": f"{fund_name} {label}", "ccy": ccy,
                "nav": rng.uniform(80, 1500), "weight": rng.uniform(0.1, 1.0),
            })
        pi_products.append(_pi_product(f_index, fund_name, fund_ccy, style, bench, pi_id, fund_id, start))
        pi_shares.extend(_pi_share(f_index, k, part, pi_id, start) for k, part in enumerate(parts))
        weight_sum = sum(p["weight"] for p in parts)
        bench_level = rng.uniform(100, 900)
        vol = 0.002 if style == "Monétaire" else 0.009
        drift = rng.uniform(-0.0002, 0.0005)

        for day in nav_days:
            shock = rng.gauss(drift, vol)
            total_eur *= 1 + shock + rng.gauss(0, 0.001)
            bench_level *= 1 + shock * 0.9 + rng.gauss(0, vol / 3)
            fx_fund = FX_TO_EUR[fund_ccy]
            total_fund_ccy = total_eur / fx_fund
            for part in parts:
                part["nav"] *= 1 + shock
                share = part["weight"] / weight_sum
                part_eur = total_eur * share
                fx_part = FX_TO_EUR[part["ccy"]]
                units = (part_eur / fx_part) / part["nav"]
                dividend = round(part["nav"] * 0.012, 4) if (day.month == 6 and day.day <= 3 and "D" not in part["name"]) else None
                aum_rows.append((
                    fund_id, pi_id, part["id"], part["pi"], part["isin"], part["name"], day.isoformat(),
                    round(part["nav"], 5), round(units, 4), None, part["ccy"], round(part_eur / fx_part, 2),
                    1.0, fund_ccy, round(part_eur / fx_fund, 2), round(total_fund_ccy, 2),
                    bench or None, round(bench_level, 5) if bench else None,
                    dividend, part["ccy"] if dividend else None,
                    round(total_eur, 2), round(part_eur, 2), load_ts,
                ))

        # inventaires mensuels
        n_lines = rng.randint(28, 60)
        pool = [ins for ins in instruments if (ins["is_bond"] if style in {"Obligations", "Monétaire", "Convertibles"} else not ins["is_bond"]) or style == "Multi-actifs"]
        chosen = rng.sample(pool, min(n_lines, len(pool)))
        raw_weights = [rng.paretovariate(1.6) for _ in chosen]
        for inv_day in inventory_days:
            aum_at = next((r for r in reversed(aum_rows) if r[0] == fund_id and r[6] <= inv_day.isoformat()), None)
            fund_total = (aum_at[15] if aum_at else 1e8) or 1e8
            weights = [w * rng.uniform(0.9, 1.1) for w in raw_weights]
            cash_weight = rng.uniform(0.005, 0.04)
            scale = (1 - cash_weight) / sum(weights)
            for ins, w in zip(chosen, weights):
                weight = w * scale
                amount_fund = fund_total * weight
                fx_ins = FX_TO_EUR[ins["currency"]] / FX_TO_EUR[fund_ccy]
                amount_ins = amount_fund / fx_ins
                price = ins["price"] * rng.uniform(0.95, 1.05)
                qty = amount_ins / (price / 100 if ins["is_bond"] else price)
                holdings_rows.append((
                    fund_id, pi_id, fund_name, fund_ccy, inv_day.isoformat(), inv_day.isoformat(),
                    ins["id"], ins["isin"], ins["bbg"], aim_code, ins["name"], ins["currency"],
                    ins["type"], ins["class"], "TITRE", round(qty, 4), round(qty, 4), round(weight, 5),
                    round(weight, 5) if ins["is_bond"] else None, round(price, 4), round(amount_ins, 4),
                    round(amount_fund, 4), round(amount_ins, 4), round(amount_fund, 4),
                    round(amount_fund / qty * rng.uniform(0.85, 1.05), 4) if qty else None,
                    ins["debt"], round(rng.uniform(0, 3), 6) if ins["is_bond"] else None,
                    round(price, 4) if ins["is_bond"] else None, round(FX_TO_EUR[ins["currency"]], 6), load_ts,
                ))
            cash = fund_total * cash_weight
            holdings_rows.append((
                fund_id, pi_id, fund_name, fund_ccy, inv_day.isoformat(), inv_day.isoformat(),
                f"CASH-{fund_ccy}", None, None, aim_code, f"Liquidités {fund_ccy}", fund_ccy,
                "CASH", "Liquidités", "CASH", round(cash, 4), round(cash, 4), round(cash_weight, 5), None,
                1.0, round(cash, 4), round(cash, 4), round(cash, 4), round(cash, 4), 1.0, None, None, None,
                round(FX_TO_EUR[fund_ccy], 6), load_ts,
            ))

    # fonds « NOMBRE_PARTS_FONDS » : somme des parts du fonds à la date
    totals: dict[tuple[str, str], float] = {}
    for row in aum_rows:
        totals[(row[0], row[6])] = totals.get((row[0], row[6]), 0.0) + row[8]
    aum_rows = [row[:9] + (round(totals[(row[0], row[6])], 4),) + row[10:] for row in aum_rows]

    conn.executemany(f"INSERT INTO JUMP_portfolio_aum VALUES ({','.join('?' * 23)})", aum_rows)
    conn.executemany(f"INSERT INTO JUMP_portfolio_holdings VALUES ({','.join('?' * 30)})", holdings_rows)
    for table, rows in (("pi_out_product_active", pi_products), ("PI_OUT_Share", pi_shares)):
        if table in catalog.tables:
            for row in rows:
                cols = ", ".join(f'"{c}"' for c in row)
                conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({",".join("?" * len(row))})', list(row.values()))
    conn.execute("CREATE INDEX ix_aum ON JUMP_portfolio_aum(CODE_ISIN_PART, DATE_VL)")
    conn.execute("CREATE INDEX ix_aum_date ON JUMP_portfolio_aum(DATE_VL)")
    conn.execute("CREATE INDEX ix_hold ON JUMP_portfolio_holdings(ID_JUMP_FONDS, DATE_INVENTAIRE)")
    conn.execute("CREATE INDEX ix_hold_isin ON JUMP_portfolio_holdings(CODE_ISIN_INSTRUMENT)")
    conn.execute("CREATE TABLE _merlin_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO _merlin_meta VALUES ('stamp', ?)", (stamp,))
    conn.commit()
    conn.close()
    tmp.replace(path)
    return path
