"""Qvidian : SOAP (sans réseau), agrégation récence × fréquence, carte des erreurs, écritures protégées, cache du compléteur.

Toutes les données sont fictives (bibliothèque de démonstration, fonds imaginaires, ISIN QZ…).
"""
from __future__ import annotations

from datetime import date

import pytest

from merlin.qvidian import soap
from merlin.qvidian.ai import build_prompts, parse_reply
from merlin.qvidian.audit import audit
from merlin.qvidian.bulk import Journal, WriteGuard, apply, make_plan, undo_plan
from merlin.qvidian.client import QvidianClient, QvidianError
from merlin.qvidian.demo import DemoQvidian
from merlin.qvidian.snapshot import Snapshot, sync
from merlin.qvidian.suggest import question_similarity, suggest
from merlin.qvidian.transport import SoapReply
from merlin.rfi.aggregate import Vote, aggregate, recency, similarity

TODAY = date(2026, 10, 15)
NS = "http://qvidian.com/webservices/"


def envelope(body: str) -> bytes:
    return (f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><soap:Body>{body}</soap:Body></soap:Envelope>').encode()


class FakeTransport:
    """Répond comme Qvidian.asmx / QvidianAuthentication.asmx, et garde chaque requête envoyée."""

    def __init__(self, expire_once: bool = False):
        self.sent: list[tuple[str, str, str]] = []
        self.expire_once = expire_once

    def post(self, url: str, body: bytes, action: str) -> SoapReply:
        op = action.rsplit("/", 1)[-1]
        xml = body.decode()
        self.sent.append((url, op, xml))
        if op in {"Connect", "ConnectByAPIKey", "ConnectByAuthToken"}:
            token = "TOKEN-2" if op == "ConnectByAuthToken" else "TOKEN-1"
            return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result><AuthToken>{token}</AuthToken><AuthUserName>demo.user</AuthUserName>'
                                           f'<QvidianURL>https://qpa.example.invalid/Qvidian.WS/Qvidian.asmx</QvidianURL></{op}Result></{op}Response>'))
        if self.expire_once and "TOKEN-1" in xml:
            self.expire_once = False
            return SoapReply(500, envelope('<soap:Fault><faultcode>soap:Server</faultcode><faultstring>x</faultstring><detail>'
                                           '<Error xmlns="http://qvidian.com/webservices"><Number>12</Number><Message>Invalid authentication token</Message>'
                                           '<Source>Qvidian</Source><Type>QvidianException</Type></Error></detail></soap:Fault>'))
        if op == "libraryFolderGetTop":
            return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result><LibraryFolderID>1</LibraryFolderID><LibraryParentFolderID>0</LibraryParentFolderID>'
                                           f'<Title>Bibliothèque</Title><ChildFolderCount>0</ChildFolderCount><ContentCount>1</ContentCount></{op}Result></{op}Response>'))
        if op == "librarySearchRequestInit":
            return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result><searchRequestUniqueID>0</searchRequestUniqueID><searchResultsCacheID>-1</searchResultsCacheID>'
                                           '<searchSettingsID>-1</searchSettingsID><searchSettingsRevision>0</searchSettingsRevision><systemSearchType>NotSet</systemSearchType>'
                                           '<resetResultsCache>false</resetResultsCache><updateSortOrder>false</updateSortOrder><resultsAsList>true</resultsAsList>'
                                           '<searchCriteria><maxResults>0</maxResults><pageSize>10</pageSize><pageIndex>0</pageIndex><offset>0</offset><sortDesc>false</sortDesc>'
                                           '<loadData>true</loadData><loadRequiredData>false</loadRequiredData><requiredPageSize>0</requiredPageSize><compressData>false</compressData>'
                                           f'<compressRequiredData>false</compressRequiredData></searchCriteria></{op}Result></{op}Response>'))
        if op == "librarySearch":
            return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result><totalCount>1</totalCount><contentDataCompressed>false</contentDataCompressed>'
                                           '<contentDataList><Content><ContentID>42</ContentID><Revision>3</Revision><Title>Politique de vote ?</Title>'
                                           '<ContentText>&lt;p&gt;Nous votons.&lt;/p&gt;</ContentText><Enabled>true</Enabled><TimesUsedCount>7</TimesUsedCount>'
                                           '<DateLastUsed>2026-09-01T10:00:00</DateLastUsed><DateToExpire xsi:nil="true" /></Content></contentDataList>'
                                           f'</{op}Result></{op}Response>'))
        if op == "libraryContentDetailsUpdate":
            return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result /></{op}Response>'))
        return SoapReply(500, envelope('<soap:Fault><faultcode>soap:Client</faultcode><faultstring>Unknown operation</faultstring></soap:Fault>'))


# ------------------------------------------------------------------ SOAP
def test_envelope_header_and_content_updates_flags():
    xml = soap.envelope("libraryContentDetailsUpdate", {"contentIDs": soap.Items("int", [1, 2]),
                                                         "contentChanges": soap.content_updates({"Enabled": False})},
                        {"AuthenticationToken": "T"}).decode()
    assert '<QvidianCredentialHeader xmlns="http://qvidian.com/webservices/"><AuthenticationToken>T</AuthenticationToken>' in xml
    assert "<contentIDs><int>1</int><int>2</int></contentIDs>" in xml
    assert "<Enabled>false</Enabled><EnabledUpdated>true</EnabledUpdated>" in xml
    assert "<TitleUpdated>false</TitleUpdated>" in xml and "<Title>" not in xml  # seul le champ demandé est modifié
    assert xml.index("<AlertEnabled>") < xml.index("<Enabled>") < xml.index("<TitleUpdated>")  # ordre du WSDL


def test_fault_becomes_plain_error():
    with pytest.raises(soap.SoapFault) as err:
        soap.parse(envelope('<soap:Fault><faultcode>soap:Server</faultcode><faultstring>boom</faultstring><detail><Error xmlns="http://qvidian.com/webservices">'
                            '<Number>7</Number><Message>Access denied</Message><Source>S</Source><Type>QvidianException</Type></Error></detail></soap:Fault>'),
                   "librarySearch")
    assert err.value.message == "Access denied" and err.value.number == "7"
    assert QvidianClient._fault(err.value).code == "permission"


# ------------------------------------------------------------------ client
def test_client_connects_then_uses_binding_url_and_token():
    t = FakeTransport()
    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport=t)
    c.connect("demo.user", "secret")
    assert c.binding.qvidian_url.endswith("/Qvidian.asmx")
    top = c.top_folder()
    assert top == {"id": 1, "parent_id": 0, "title": "Bibliothèque", "children": 0, "contents": 1, "enabled": True}
    url, op, xml = t.sent[-1]
    assert url.endswith("/Qvidian.asmx") and op == "libraryFolderGetTop" and "<AuthenticationToken>TOKEN-1</AuthenticationToken>" in xml
    assert "secret" in t.sent[0][2] and all("secret" not in x for _, _, x in t.sent[1:])  # mot de passe envoyé une seule fois


def test_search_reuses_server_initialised_request():
    t = FakeTransport()
    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport=t)
    c.connect("demo.user", "secret")
    total, items = c.search("politique de vote", size=25)
    sent = next(x for _, op, x in t.sent if op == "librarySearch")
    assert "<librarySearchRequest>" in sent and "<terms>politique de vote</terms>" in sent
    assert "<pageSize>25</pageSize>" in sent and "<string>ContentText</string>" in sent and "<eSearchFoundIns>Title</eSearchFoundIns>" in sent
    assert sent.index("<searchTermsCriteria>") < sent.index("<searchCriteria>")  # ordre du WSDL respecté à l'insertion
    assert total == 1 and items[0]["id"] == 42 and items[0]["text"] == "Nous votons." and items[0]["times_used"] == 7
    assert items[0]["last_used"] == "2026-09-01" and items[0]["expires"] is None


def test_expired_token_reconnects_once():
    t = FakeTransport(expire_once=True)
    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport=t)
    c.connect("demo.user", "secret")
    assert c.top_folder()["id"] == 1
    assert [op for _, op, _ in t.sent] == ["Connect", "libraryFolderGetTop", "ConnectByAuthToken", "libraryFolderGetTop"]
    assert c.binding.token == "TOKEN-2"


# ------------------------------------------------------------------ agrégation
def test_recent_choice_beats_old_popular_one_and_latest_version_wins():
    votes = [Vote("Ancienne rédaction de la politique de vote, publiée chaque année avec un rapport.", "qvidian", uses=30, when=date(2022, 4, 1)),
             Vote("Nouvelle rédaction : nous votons à toutes les assemblées, politique revue chaque année.", "qvidian", uses=8, when=date(2026, 9, 25))]
    best = aggregate(votes, today=TODAY)
    assert best[0].value.startswith("Nouvelle") and best[0].share > 0.8
    assert recency(date(2025, 10, 15), TODAY) == pytest.approx(0.5, abs=0.01)  # demi-vie d'un an


def test_versions_of_a_text_are_grouped():
    a = "Société de Gestion Imaginaire est une société de gestion indépendante fondée en 1998, agréée par l'AMF."
    b = "Société de Gestion Imaginaire est une société de gestion indépendante créée en 1998 et agréée par l'AMF."
    assert similarity(a, b) >= 0.5
    choices = aggregate([Vote(a, "qvidian", when=date(2026, 9, 1)), Vote(b, "precedent", when=date(2024, 1, 1))], today=TODAY)
    assert len(choices) == 1 and choices[0].versions == 2 and choices[0].value == a  # la plus récente
    assert aggregate([Vote("Oui", "fabric"), Vote("Non", "precedent", when=TODAY)], today=TODAY)[0].value == "Oui"  # réponses courtes : exactes


@pytest.fixture(scope="module")
def demo_snapshot(tmp_path_factory):
    snap = Snapshot(tmp_path_factory.mktemp("qv") / "demo.sqlite")
    sync(DemoQvidian(), snap, "demo")
    return snap


def test_suggest_keeps_same_question_and_ranks_by_recency(demo_snapshot):
    vote = suggest(demo_snapshot, "Quelle est votre politique de vote ?", today=TODAY)
    assert vote[0].value.startswith("Nous votons à toutes les assemblées")  # 8 utilisations récentes > 30 anciennes
    company = suggest(demo_snapshot, "Présentez la société de gestion", today=TODAY)
    assert len(company) == 1 and company[0].versions == 2 and "fondée en 1998" in company[0].value
    aum = suggest(demo_snapshot, "Quel est l'encours de la société de gestion ?", today=TODAY)
    assert all("encours" in c.value for c in aum)  # une question voisine moins proche n'est pas mélangée
    assert question_similarity("Qui est le dépositaire ?", "Quel est le dépositaire du fonds ?") > 0.45


# ------------------------------------------------------------------ carte des erreurs
def test_error_map_finds_each_kind_of_problem(demo_snapshot):
    r = audit(demo_snapshot.all(), today=TODAY)
    by_id = {it["id"]: {i["category"] for i in it["issues"]} for it in r["items"]}
    assert {"code", "doublon"} <= by_id[1005]  # &lt;br&gt; et {{NOM_DIRIGEANT}}
    assert "code" in by_id[1019] and "code" in by_id[1007]  # #REF!, [object Object], mise en forme collée
    assert "depasse" in by_id[1015] and "expire" in by_id[1015]  # EONIA, contenu expiré
    assert "depasse" in by_id[1011] and "depasse" in by_id[1003]  # DICI, chiffre daté de 2019
    assert "provisoire" in by_id[1009] and "langue" in by_id[1017] and "expire" in by_id[1016]
    assert not by_id[1018] and not by_id[1006]  # contenus sains : rien à signaler
    groups = {g["group"]: g for g in r["groups"]}
    assert groups["Société / Gouvernance"]["counts"]["code"] == 1


def test_ai_round_trip():
    contents = [{"id": 1003, "title": "Encours ?", "text": "Au 31/12/2019 …", "folder_path": "Société", "modified": "2020-01-15"}]
    prompt = build_prompts(contents, today="15/10/2026")["batches"][0]["prompt"]
    assert "C1003 — Question : Encours ?" in prompt and "| ID | Catégorie | Gravité | Problème | Correction proposée |" in prompt
    reply = "| ID | Catégorie | Gravité | Problème | Correction |\n|---|---|---|---|---|\n| C1003 | dépassé | haute | Encours de 2019. | Mettre à jour. |\n| C9 | code | basse | x | y |"
    out = parse_reply(reply, [1003])
    assert out["read"] == 1 and out["unknown"] == ["C9"]
    assert out["findings"][1003][0] == {"kind": "dépassé", "severity": "haute", "problem": "Encours de 2019.", "fix": "Mettre à jour."}


# ------------------------------------------------------------------ écritures protégées
def test_bulk_needs_password_skips_alerts_unless_forced_and_can_undo(tmp_path):
    client = DemoQvidian()
    snap = Snapshot(tmp_path / "demo.sqlite")
    sync(client, snap, "demo")
    guard = WriteGuard("mot-de-passe-de-test")
    journal = Journal(tmp_path / "journal.jsonl")
    client.contents[1007]["CheckedOut"] = "true"
    client.contents[1007]["CheckedOutByUserName"] = "Collègue démo"
    plan = make_plan(snap.many([1003, 1007, 1009]), "disable", {})
    assert [i.id for i in plan.items] == [1003, 1007, 1009] and plan.public()["warnings"] == 0  # instantané : pas encore extrait
    with pytest.raises(QvidianError) as err:
        guard.verify("faux")
    assert err.value.code == "mot-de-passe" and client.writes == []
    guard.verify("mot-de-passe-de-test")
    r = apply(client, plan, force=False, user="test", journal=journal, source="demo")
    assert r["written"] == 2 and r["skipped"] == 1  # 1007 extrait par quelqu'un : laissé de côté
    assert client.contents[1003]["Enabled"] == "false" and client.contents[1007]["Enabled"] == "true"
    forced = apply(client, make_plan(snap.many([1007]), "disable", {}), force=True, user="test", journal=journal, source="demo")
    assert forced["written"] == 1 and client.contents[1007]["Enabled"] == "false"
    entry = journal.get(r["batch"])
    assert entry["items"][0]["before"] is True and entry["items"][0]["after"] is False
    undo = apply(client, undo_plan(entry), force=True, user="test", journal=journal, source="demo", undo_of=r["batch"])
    assert undo["written"] == 2 and client.contents[1003]["Enabled"] == "true"


def test_password_locks_after_repeated_failures():
    guard = WriteGuard("secret-de-test")
    for _ in range(5):
        with pytest.raises(QvidianError):
            guard.verify("non")
    with pytest.raises(QvidianError) as err:
        guard.verify("secret-de-test")
    assert err.value.code == "verrou"
    assert not WriteGuard("").configured


def test_text_replace_preview_and_warning_for_file_content(tmp_path):
    client = DemoQvidian()
    snap = Snapshot(tmp_path / "demo.sqlite")
    sync(client, snap, "demo")
    plan = make_plan(snap.all(), "replace_text", {"find": "DICI", "replace": "DIC PRIIPs", "case": True})
    assert [i.id for i in plan.items] == [1011]
    assert "DIC PRIIPs" in plan.items[0].public()["after"] and not plan.items[0].warnings  # contenu éditable en ligne


# ------------------------------------------------------------------ API
def test_api_window_flow(client):
    from merlin.api.qvidian import service as qvidian_service
    from merlin.state import get_state

    status = client.get("/api/qvidian/status").json()
    assert status["mode"] == "demo" and status["write_enabled"] is False
    a = client.get("/api/qvidian/audit").json()
    assert a["contents"] == 20 and any(c["key"] == "code" and c["count"] >= 3 for c in a["categories"])
    s = client.get("/api/qvidian/suggest", params={"q": "Quelle est votre politique de vote ?"}).json()
    assert s["choices"][0]["value"].startswith("Nous votons à toutes")
    plan = client.post("/api/qvidian/bulk/plan", json={"ids": [1009], "action": "disable"}).json()
    refused = client.post("/api/qvidian/bulk/apply", json={"plan_id": plan["id"], "password": "x"})
    assert refused.status_code == 400 and "désactivée" in refused.json()["detail"]["message"]  # aucun mot de passe défini
    svc = qvidian_service(get_state())
    svc.guard = WriteGuard("mot-de-passe-de-test")
    wrong = client.post("/api/qvidian/bulk/apply", json={"plan_id": plan["id"], "password": "x"})
    assert wrong.status_code == 400 and "incorrect" in wrong.json()["detail"]["message"]
    ok = client.post("/api/qvidian/bulk/apply", json={"plan_id": plan["id"], "password": "mot-de-passe-de-test"}).json()
    assert ok["written"] == 1 and client.get("/api/qvidian/contents/1009").json()["enabled"] is False
    journal = client.get("/api/qvidian/journal").json()
    undone = client.post(f"/api/qvidian/journal/{journal[0]['batch']}/undo", json={"password": "mot-de-passe-de-test"}).json()
    assert undone["written"] == 1 and client.get("/api/qvidian/contents/1009").json()["enabled"] is True
    svc.guard = WriteGuard("")


# ------------------------------------------------------------------ compléteur : choisir ne recalcule qu'une case
def test_choose_recomputes_only_the_chosen_cell(client, monkeypatch):
    import merlin.rfi.service as service

    doc = client.post("/api/rfi/demo/xlsx").json()
    s = doc["suggestions"][0]
    body = {"pid": s["pid"], "isin": s["isin"], "as_of": "2026-10-15", "fresh": True}
    first = client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()
    assert all("choices" in q for q in first["questions"])
    calls = []
    original = service._analyze_slot
    monkeypatch.setattr(service, "_analyze_slot", lambda *a, **k: calls.append(a[2].id) or original(*a, **k))
    target = next(q for q in first["questions"] if q["choices"])
    chosen = target["choices"][-1]["value"]
    second = client.post(f"/api/rfi/documents/{doc['id']}/answers",
                         json={**body, "fresh": False, "overrides": {target["id"]: {"text": chosen}}}).json()
    assert calls == [target["id"]]  # une seule case recalculée (avant : toutes)
    row = next(q for q in second["questions"] if q["id"] == target["id"])
    assert row["answer"] == chosen and row["choices"][0]["value"] == chosen  # votre choix passe en tête, les autres sources restent
    assert len(row["choices"]) >= len(target["choices"]) - 1
    calls.clear()
    client.post(f"/api/rfi/documents/{doc['id']}/answers", json={**body, "fresh": True})
    assert len(calls) == len(first["questions"])  # « Analyser » : tout est relu


def test_expired_session_asks_to_reconnect_and_object_errors_are_raised():
    class Expired(FakeTransport):
        def post(self, url, body, action):
            op = action.rsplit("/", 1)[-1]
            if op == "ConnectByAuthToken":
                return SoapReply(500, envelope('<soap:Fault><faultcode>soap:Server</faultcode><faultstring>Invalid authentication token</faultstring></soap:Fault>'))
            if op == "libraryContentDetailsGet":
                return SoapReply(200, envelope(f'<{op}Response xmlns="{NS}"><{op}Result><ContentID>0</ContentID><HasErrors>true</HasErrors>'
                                               f'<errors><int>1007</int></errors></{op}Result></{op}Response>'))
            return super().post(url, body, action)

    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport=Expired())
    c.connect("demo.user", "secret")
    with pytest.raises(QvidianError) as err:
        c.content(5)
    assert "1007" in err.value.message  # HasErrors : erreur signalée dans l'objet (guide « Error Handling »)
    c.transport.expire_once = True
    with pytest.raises(QvidianError) as err:
        c.top_folder()
    assert err.value.code == "session" and c.binding is None and not c.connected


def test_sso_callback_tolerates_plus_turned_into_space(tmp_path):
    import base64

    from merlin.config import QvidianSettings
    from merlin.qvidian.service import QvidianService, _from_b64

    token = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    b64 = base64.b64encode(("é" + token).encode()).decode()
    assert "+" in base64.b64encode(b"\xfb\xef").decode()
    assert _from_b64(b64.replace("+", " ")) == "é" + token
    assert _from_b64(base64.b64encode(b"demo.user@example.invalid").decode().rstrip("=")) == "demo.user@example.invalid"
    assert _from_b64("deja-en-clair") == "deja-en-clair"
    svc = QvidianService(QvidianSettings(auth_url="https://login.example.invalid/QvidianAuthentication.asmx"), tmp_path)

    class Refuse:
        def __init__(self, *_):
            pass

        def connect_token(self, user, tok):
            raise QvidianError("auth", "Connexion Qvidian refusée")

    import merlin.qvidian.service as service_module
    original = service_module.QvidianClient
    service_module.QvidianClient = Refuse
    try:
        with pytest.raises(QvidianError):
            svc.sso_callback(base64.b64encode(token.encode()).decode(), base64.b64encode(b"demo.user").decode())
    finally:
        service_module.QvidianClient = original
    assert "demo.user" in svc.last_sso_error and token not in svc.last_sso_error
    assert token not in (tmp_path / "qvidian" / "sso.log").read_text()


def test_big_folder_falls_back_to_paged_search(tmp_path):
    class Big(DemoQvidian):
        def folder_contents(self, folder_id):
            items = super().folder_contents(folder_id)
            return items[:1] if folder_id == 11 else items  # liste du dossier tronquée

        def folder_contents_paged(self, folder_id, size=200, limit=20000):
            self.paged = folder_id
            return super().folder_contents(folder_id)

    client = Big()
    snap = Snapshot(tmp_path / "s.sqlite")
    sync(client, snap, "demo")
    assert client.paged == 11 and {1001, 1002, 1003} <= {c["id"] for c in snap.all()}


def test_folder_filter_is_sent_in_wsdl_order():
    t = FakeTransport()
    c = QvidianClient("https://login.example.invalid/QvidianAuthentication.asmx", transport=t)
    c.connect("demo.user", "secret")
    c.search(size=10, filters=[soap.folder_filter(51)])
    sent = next(x for _, op, x in t.sent if op == "librarySearch")
    assert "<filtersAND><FilterCriteria><classType>Standard</classType><propType>Property</propType>" in sent
    assert "<fieldName>LibraryFolderID</fieldName>" in sent and "<values><string>51</string></values>" in sent
    assert sent.index("<pageIndex>") < sent.index("<filtersAND>") < sent.index("<searchFields>")
