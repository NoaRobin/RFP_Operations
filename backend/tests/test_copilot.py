"""Aller-retour Copilot : pack (classeur + consignes), réimport en « à vérifier » uniquement, garde-fous."""
import io
import zipfile

from openpyxl import load_workbook


def _doc(client):
    doc = client.post("/api/rfi/demo/xlsx").json()
    s = doc["suggestions"][0]
    return doc, {"pid": s["pid"], "isin": s["isin"]}


def test_pack_then_answers_come_back_as_review_never_auto(client):
    doc, body = _doc(client)
    r = client.post(f"/api/rfi/documents/{doc['id']}/copilot-pack", json=body)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"Questions_Copilot.xlsx", "LISEZ-MOI.txt"} <= set(zf.namelist())
    wb = load_workbook(io.BytesIO(zf.read("Questions_Copilot.xlsx")))
    assert "NON TROUVÉ" in wb["Consignes Copilot"]["A3"].value
    ws = wb["Questions"]
    header = [c.value for c in ws[1]]
    rows = list(ws.iter_rows(min_row=2))
    assert rows, "le pack doit contenir les questions à confirmer"
    i_ans, i_src, i_opt = header.index("Réponse Copilot"), header.index("Source citée (document, page)"), header.index("Options autorisées")
    open_row = next(r for r in rows if not r[i_opt].value)
    no_source = next(r for r in rows if r is not open_row and not r[i_opt].value) if sum(1 for r in rows if not r[i_opt].value) > 1 else None
    open_row[i_ans].value, open_row[i_src].value = "Réponse fictive confirmée", "DIC p. 2"
    if no_source is not None:
        no_source[i_ans].value = "Sans citation"
    buf = io.BytesIO()
    wb.save(buf)

    back = client.post(f"/api/rfi/documents/{doc['id']}/copilot-answers", params=body,
                       files={"file": ("Questions_Copilot.xlsx", buf.getvalue(), "application/octet-stream")}).json()
    qid = open_row[0].value
    assert back["overrides"][qid]["text"] == "Réponse fictive confirmée" and back["overrides"][qid]["citation"] == "DIC p. 2"
    if no_source is not None:
        assert any(x["id"] == no_source[0].value and "source" in x["reason"] for x in back["rejected"])

    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json={**body, "overrides": back["overrides"]}).json()
    row = next(q for q in analysis["questions"] if q["id"] == qid)
    assert row["status"] == "review" and row["source"] == "Copilot" and "DIC p. 2" in row["evidence"]


def test_option_outside_client_list_is_refused(client):
    doc, body = _doc(client)
    r = client.post(f"/api/rfi/documents/{doc['id']}/copilot-pack", json={**body}, params={"include_auto": True})
    wb = load_workbook(io.BytesIO(zipfile.ZipFile(io.BytesIO(r.content)).read("Questions_Copilot.xlsx")))
    ws = wb["Questions"]
    header = [c.value for c in ws[1]]
    i_opt = header.index("Options autorisées")
    row = next(r for r in ws.iter_rows(min_row=2) if r[i_opt].value)
    row[header.index("Réponse Copilot")].value = "Option imaginaire"
    row[header.index("Source citée (document, page)")].value = "Prospectus p. 12"
    buf = io.BytesIO()
    wb.save(buf)
    back = client.post(f"/api/rfi/documents/{doc['id']}/copilot-answers", params=body,
                       files={"file": ("q.xlsx", buf.getvalue(), "application/octet-stream")}).json()
    assert row[0].value not in back["overrides"]
    assert any("choix du client" in x["reason"] for x in back["rejected"])


def test_copy_paste_flow_prompt_then_reply(client):
    doc, body = _doc(client)
    out = client.post(f"/api/rfi/documents/{doc['id']}/copilot-prompt", json=body).json()
    assert out["count"] > 0 and out["batches"]
    prompt = out["batches"][0]["prompt"]
    # le format de retour est imposé, avec un exemple, et les règles anti-invention
    assert "| ID | Réponse | Source | Confiance |" in prompt and "NON TROUVÉ" in prompt and "Q1 —" in prompt
    labels = out["labels"]
    q_free = next(lbl for lbl, qid in labels.items() if not _question(client, doc, body, qid)["options"])
    q_opt = next((lbl for lbl, qid in labels.items() if _question(client, doc, body, qid)["options"]), None)
    reply = "Voici le tableau :\n| ID | Réponse | Source | Confiance |\n|---|---|---|---|\n"
    reply += f"| **{q_free}** | Réponse fictive | DIC p.2 | Haute |\n"
    if q_opt:
        reply += f"| {q_opt} | Option imaginaire | Prospectus p.9 | moyenne |\n"
    reply += "| Q999 | x | y | z |\n"
    r = client.post(f"/api/rfi/documents/{doc['id']}/copilot-reply", json={**body, "text": reply, "labels": labels}).json()
    assert r["overrides"][labels[q_free]]["citation"] == "DIC p.2" and r["unknown"] == ["Q999"]
    if q_opt:
        assert any(x["verdict"] == "rejected" and "choix" in x["reason"] for x in r["lines"])
    analysis = client.post(f"/api/rfi/documents/{doc['id']}/answers", json={**body, "overrides": r["overrides"]}).json()
    row = next(q for q in analysis["questions"] if q["id"] == labels[q_free])
    assert row["status"] == "review" and row["source"] == "Copilot"  # jamais automatique
    bad = client.post(f"/api/rfi/documents/{doc['id']}/copilot-reply", json={**body, "text": "Je n'ai pas trouvé.", "labels": labels})
    assert bad.status_code == 400 and "tableau" in bad.json()["detail"]["hint"]


_cache: dict = {}


def _question(client, doc, body, qid):
    if doc["id"] not in _cache:
        _cache[doc["id"]] = {q["id"]: q for q in client.post(f"/api/rfi/documents/{doc['id']}/answers", json=body).json()["questions"]}
    return _cache[doc["id"]][qid]
