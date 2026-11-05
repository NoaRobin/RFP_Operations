"""Mémoire des réponses (Pit Stop) et fiche fonds (Atelier) : données fictives."""


def test_memory_values_past_answers(client):
    client.post("/api/qvidian/history/rebuild")
    m = client.get("/api/qvidian/memory").json()
    assert m["rfis"] >= 5 and m["links"] >= 20 and 0 < m["reuse_rate"] <= 1
    assert m["pillars"] and m["pillars"][0]["rfis"] >= m["pillars"][-1]["rfis"]  # les plus réutilisés d'abord
    assert m["timeline"] and all(x["answers"] > 0 for x in m["timeline"])
    assert m["unused_total"] == len(m["unused"]) or m["unused_total"] > len(m["unused"])


def test_fund_sheet_reads_product_info_and_jump(client):
    isin = next(s["isin"] for f in client.get("/api/rfi/funds?q=").json() for s in f["shares"])
    sheet = client.get(f"/api/atelier/fund-sheet?isin={isin}").json()
    assert sheet["isin"] == isin and sheet["filled"] > 50 and {"Fonds", "Part"} <= set(sheet["groups"])
    item = next(x for x in sheet["groups"]["Part"] if x["has_value"])
    assert item["display"] and item["source"]
    assert client.get(f"/api/atelier/fund-sheet.xlsx?isin={isin}").content[:2] == b"PK"
    assert client.get("/api/atelier/fund-sheet?isin=QZ0000000000").status_code == 404


def test_qviapi_workshop(client):
    from datetime import date

    from merlin.qvidian.workshop import review_date

    f = client.get("/api/qvidian/freshness").json()
    assert f["items"] and sum(f["counts"].values()) == len(f["items"])
    assert all(f["items"][i]["days"] <= f["items"][i + 1]["days"] for i in range(len(f["items"]) - 1))
    d, why = review_date({"text": "Encours de 12 milliards d'euros au 31/12/2025.", "modified": "2026-01-15"}, date(2026, 11, 5))
    assert d.isoformat() == "2026-04-30" and "trimestriel" in why
    assert "deux ans" in review_date({"text": "Notre philosophie de gestion.", "modified": "2026-01-15"}, date(2026, 11, 5))[1]
    fam = client.get("/api/qvidian/families").json()
    assert all(sum(m["keep"] for m in x["members"]) == 1 and x["size"] >= 2 for x in fam)
    client.post("/api/qvidian/history/rebuild")
    bank = client.get("/api/qvidian/questions").json()
    assert bank["ready"] and bank["items"] and bank["items"][0]["rfis"] >= bank["items"][-1]["rfis"]
    ids = [x["id"] for x in f["items"][:3]]
    assert client.post("/api/qvidian/export.xlsx", json={"ids": ids}).content[:2] == b"PK"
