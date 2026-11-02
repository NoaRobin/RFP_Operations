"""Recherche sémantique Qvidian : analyse du texte, moteur hybride, niveaux société / fonds / part, utilisations,
qualité mesurée (nDCG) sur la bibliothèque de démonstration, optimisation des appels, synchronisation incrémentale."""
import os
from datetime import date
from pathlib import Path

import pytest
import yaml

from merlin.qvidian.demo import DemoQvidian
from merlin.qvidian.evaluate import TODAY, run
from merlin.qvidian.levels import FundNames, classify
from merlin.qvidian.library_search import LibrarySearch
from merlin.qvidian.snapshot import Snapshot, sync
from merlin.qvidian.telemetry import RateLimiter, Telemetry, TtlCache
from merlin.search.engine import mrr, ndcg
from merlin.search.text import snippet, stem, terms
from merlin.search.thesaurus import expand

TESTS = Path(__file__).parent


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    snap = Snapshot(tmp_path_factory.mktemp("search") / "demo.sqlite")
    sync(DemoQvidian(), snap, "demo")
    return LibrarySearch(snap, today=TODAY)


# ------------------------------------------------------------------ analyse du texte
def test_stemming_joins_inflections_without_merging_distinct_words():
    assert stem("rémunérés".replace("é", "e")) == stem("remuneration") == stem("remunerations")
    assert stem("selectionnez") == stem("selection")
    assert stem("politiques") == stem("politique") and stem("liquidite") == stem("liquidity")
    assert stem("gestion") != stem("gestionnaire")
    assert terms("Avez-vous un PCA ?") == ["pca"]  # « avez », « vous », « un » ne portent pas le sujet


def test_thesaurus_brings_cross_language_equivalents():
    added, matched, equivalents = expand(terms("Who owns the company?"))
    assert "actionnariat" in added and matched
    added, _, _ = expand(terms("Avez-vous un PCA ?"))
    assert "continuit" in " ".join(added) or "bcp" in added


def test_snippet_highlights_query_words():
    text = "Le plan de continuité d'activité prévoit un site de repli et un test complet chaque année."
    snip, spans = snippet(text, set(terms("site de repli")))
    assert "repli" in snip and any(snip[a:b].lower() == "repli" for a, b in spans)


def test_ranking_metrics():
    assert ndcg([1, 2, 3], {1: 2}) == 1.0 and ndcg([2, 1], {1: 2}) < 1.0
    assert mrr([5, 1], {1}) == 0.5


# ------------------------------------------------------------------ niveaux
def test_levels_company_fund_share():
    funds = FundNames(["Fonds Imaginaire Horizon", "Fonds Imaginaire Aurore"])
    assert funds.find("le fonds Aurore") == ["Fonds Imaginaire Aurore"]
    assert funds.find("Fonds Imaginaire") == []  # mot commun aux deux fonds : jamais deviné
    company = classify("Qui sont les actionnaires de la société ?", "Le capital est détenu à 62 % par les associés.", "Société / Présentation", funds)
    assert company.scope == "societe"
    share = classify("Quel est le minimum de souscription de la part I du Fonds Imaginaire Horizon ?",
                     "La part I (ISIN QZ0000000037) a un minimum de 1 000 000 EUR.", "Fonds / Fonds Imaginaire Horizon", funds)
    assert share.scope == "part" and share.funds == ["Fonds Imaginaire Horizon"] and share.isins == ["QZ0000000037"]
    fund = classify("Décrivez le processus de gestion du Fonds Imaginaire Aurore.", "Fonds obligataire euro.", "Fonds / Fonds Imaginaire Aurore", funds)
    assert fund.scope == "fonds" and "gestion" in fund.themes


def test_engine_classifies_the_demo_library(engine):
    by_id = {c["id"]: lv for c, lv in zip(engine.rows, engine.levels)}
    assert by_id[1021].scope == "societe" and by_id[1052].scope == "part" and by_id[1054].funds == ["Fonds Imaginaire Aurore"]
    assert "Fonds Imaginaire Boréal" in engine.funds.names


# ------------------------------------------------------------------ recherche
def test_question_about_one_fund_never_surfaces_another_funds_text_first(engine):
    res = engine.search("Indicateur de référence du fonds Aurore")
    assert res["results"][0]["id"] == 1055
    ids = [r["id"] for r in res["results"]]
    assert 1051 not in ids[:3]  # le benchmark d'Horizon est repoussé
    assert res["level"]["funds"] == ["Fonds Imaginaire Aurore"]


def test_cross_language_and_paraphrase(engine):
    assert engine.search("Who owns the company?")["results"][0]["id"] in {1021, 1060}
    assert engine.search("Avez-vous un PCA ?")["results"][0]["id"] in {1031, 1062}
    assert engine.search("Comment sont rémunérés les gérants ?")["results"][0]["id"] == 1030


def test_versions_are_grouped_and_usage_explained(engine):
    res = engine.search("Présentez votre société de gestion")
    top = res["results"][0]
    assert top["id"] in {1001, 1002} and {v["id"] for v in top["variants"]} & {1001, 1002}
    assert any("utilisé" in w for w in top["why"]) and top["times_used"] > 0
    assert top["level"]["scope"] == "societe" and res["facets"]["scope"]


def test_filters_and_sorting(engine):
    res = engine.search("politique", filters={"scope": ["societe"]})
    assert all(r["level"]["scope"] == "societe" for r in res["results"])
    browse = engine.search("", sort="utilisations", k=5)
    uses = [r["times_used"] for r in browse["results"]]
    assert uses == sorted(uses, reverse=True) and browse["total"] > 50
    english = engine.search("exclusion", filters={"language": "en"})
    assert english["results"] and all(r["language"] == "en" for r in english["results"])
    assert not any(r["id"] == 1068 for r in engine.search("stagiaires")["results"][:1] if r["issues"] == [])


def test_measured_quality_lexical_mode(engine):
    """Qualité mesurée sans modèle neuronal (seuils minimaux ; la mesure complète : python -m merlin.qvidian.evaluate)."""
    tuning = yaml.safe_load((TESTS / "qvidian_search_eval.yaml").read_text(encoding="utf-8"))["queries"]
    holdout = yaml.safe_load((TESTS / "qvidian_search_holdout.yaml").read_text(encoding="utf-8"))["queries"]
    a, b = run(engine, tuning), run(engine, holdout)
    assert a["ndcg@10"] >= 0.93 and a["mrr@10"] >= 0.9
    assert b["ndcg@10"] >= 0.87 and b["recall@20"] >= 0.95  # jeu jamais vu au réglage


def test_similar_contents(engine):
    info = engine.describe(1041)
    assert info["level"]["scope"] in {"societe", "generique"} and any(s["id"] == 1064 for s in info["similar"])


@pytest.mark.skipif(not os.environ.get("MERLIN_TEST_MODELS"), reason="modèles ONNX non fournis (MERLIN_TEST_MODELS=dossier)")
def test_neural_stack_improves_or_keeps_quality(tmp_path):
    from merlin.search import neural

    root = Path(os.environ["MERLIN_TEST_MODELS"])
    snap = Snapshot(tmp_path / "demo.sqlite")
    sync(DemoQvidian(), snap, "demo")
    holdout = yaml.safe_load((TESTS / "qvidian_search_holdout.yaml").read_text(encoding="utf-8"))["queries"]
    lexical = run(LibrarySearch(snap, today=TODAY), holdout)["ndcg@10"]
    full = LibrarySearch(snap, encoder=neural.Encoder(root, "e5-small"), reranker=neural.Reranker(root), today=TODAY)
    assert run(full, holdout)["ndcg@10"] >= lexical
    assert (tmp_path / "demo.e5-small.vectors.npz").exists()  # vecteurs gardés : seuls les textes modifiés seront réencodés


# ------------------------------------------------------------------ optimisation des appels
def test_telemetry_cache_and_limiter():
    t = Telemetry()
    for ms in (10, 20, 30, 400):
        t.record("librarySearch", ms, bytes_in=2048)
    t.record("libraryContentDetailsGet", 0, cached=True)
    t.record("librarySearch", 5, ok=False, code="delai")
    s = t.summary()
    op = next(o for o in s["operations"] if o["op"] == "librarySearch")
    assert op["calls"] == 5 and op["errors"] == 1 and op["p95_ms"] >= 30 and s["cache_rate"] > 0
    cache = TtlCache(60)
    cache.put(("libraryContentDetailsGet", (("contentID", "7"),)), {"ok": 1})
    assert cache.get(("libraryContentDetailsGet", (("contentID", "7"),)))[0]
    assert cache.invalidate(lambda k: ("contentID", "7") in k[1]) == 1
    limiter = RateLimiter(50, 2)
    assert limiter.acquire() == 0.0 and limiter.acquire() == 0.0 and limiter.acquire() > 0


def test_client_caches_reads_retries_and_invalidates_after_write():
    from merlin.qvidian.client import Binding, QvidianClient
    from merlin.qvidian.transport import NetError, SoapReply

    detail = (b'<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
              b'<libraryContentDetailsGetResponse xmlns="http://qvidian.com/webservices/"><libraryContentDetailsGetResult>'
              b'<ContentID>7</ContentID><Title>T</Title><Revision>1</Revision></libraryContentDetailsGetResult>'
              b'</libraryContentDetailsGetResponse></soap:Body></soap:Envelope>')
    update = (b'<?xml version="1.0"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
              b'<libraryContentDetailsUpdateResponse xmlns="http://qvidian.com/webservices/"><libraryContentDetailsUpdateResult />'
              b'</libraryContentDetailsUpdateResponse></soap:Body></soap:Envelope>')

    class Flaky:
        def __init__(self):
            self.calls = []

        def post(self, url, body, action):
            self.calls.append(action)
            if len(self.calls) == 1:
                raise NetError("delai", "timeout", "qvidian.example.invalid")
            return SoapReply(200, update if action.endswith("Update") else detail)

    transport = Flaky()
    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport).configure(300, 1000)
    c.binding = Binding("TOKEN", "user", "https://qpa.example.invalid/Qvidian.asmx", {})
    assert c.content(7)["title"] == "T" and len(transport.calls) == 2  # coupure : relancée une fois
    assert c.content(7)["title"] == "T" and len(transport.calls) == 2  # deuxième lecture : cache
    c.update_details([7], {"Enabled": False})
    c.content(7)
    assert len(transport.calls) == 4  # écriture : jamais relancée, cache du contenu 7 invalidé
    stats = c.telemetry.summary()
    assert stats["cached"] == 1 and any(o["op"] == "libraryContentDetailsGet" and o["retries"] == 1 for o in stats["operations"])


def test_incremental_sync_picks_changes_and_deletions(tmp_path):
    client = DemoQvidian()
    snap = Snapshot(tmp_path / "s.sqlite")
    full = sync(client, snap, "demo", workers=4)
    assert full["mode"] == "full" and full["contents"] == len(client.contents)
    snap.set_meta({"synced_at": "2026-10-14T10:00:00"})
    client.contents[1001]["ContentText"] = "Texte mis à jour."
    client.contents[1001]["DateLastModified"] = "2026-10-15T09:00:00"
    del client.contents[1068]
    delta = sync(client, snap, "demo", mode="delta")
    assert delta["mode"] == "delta" and delta["removed"] == 1 and delta["changed"] >= 1
    assert snap.get(1001)["text"] == "Texte mis à jour." and snap.get(1068) is None


# ------------------------------------------------------------------ API
def test_search_api_and_engine_status(client):
    res = client.post("/api/qvidian/search", json={"q": "Who owns the company?", "k": 5}).json()
    assert res["results"] and res["results"][0]["level"]["scope_label"] and "timings" in res
    assert client.post("/api/qvidian/search", json={"q": "", "sort": "utilisations"}).json()["total"] > 50
    detail = client.get(f"/api/qvidian/contents/{res['results'][0]['id']}").json()
    assert detail["insight"]["level"]["scope"] and isinstance(detail["insight"]["similar"], list)
    eng = client.get("/api/qvidian/engine").json()
    assert eng["ready"] and any(m["id"] == "e5-small" for m in eng["models"])
    stats = client.get("/api/qvidian/api-stats").json()
    assert stats["settings"]["concurrency"] >= 1 and stats["telemetry"]["calls"] >= 1
    assert client.get("/api/qvidian/overview").json()["top_used"]


def test_new_write_actions_need_preview_then_password(client):
    plan = client.post("/api/qvidian/bulk/plan", json={"ids": [1044], "action": "add_terms", "params": {"text": "UNPRI, signataire"}}).json()
    assert plan["items"][0]["after"].endswith("UNPRI, signataire")
    moved = client.post("/api/qvidian/bulk/plan", json={"ids": [1044, 1045], "action": "move", "params": {"folder_id": 62, "folder_label": "English library / Funds (EN)"}}).json()
    assert len(moved["items"]) == 2 and moved["items"][0]["after"] == "English library / Funds (EN)"
    bad = client.post("/api/qvidian/bulk/plan", json={"ids": [1044, 1045], "action": "set_text", "params": {"text": "x"}})
    assert bad.status_code == 400  # réécriture : un seul contenu à la fois
    refused = client.post("/api/qvidian/bulk/apply", json={"plan_id": plan["id"], "password": "faux"})
    assert refused.status_code == 400
    _ = date.today()
