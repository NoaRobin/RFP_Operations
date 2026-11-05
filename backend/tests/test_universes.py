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
