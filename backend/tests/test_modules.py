"""RFI, merge codes Qvidian et suivi d'activité (données fictives)."""
import io
import zipfile

import docx
from openpyxl import load_workbook


def test_mergecodes_demo(client):
    analysis = client.post("/api/mergecodes/demo").json()
    assert len(analysis["candidats"]) == 6
    decisions = [{"choix": "proposition", "proposition": 1}] * 5 + [{"choix": "ignorer"}]
    result = client.post(f"/api/mergecodes/documents/{analysis['id']}/appliquer", json={"decisions": decisions}).json()
    assert result["inseres"] == 5
    d = docx.Document(io.BytesIO(client.get(result["document_url"]).content))
    assert "<<XPINDUS_VLac>>" in "\n".join(p.text for p in d.paragraphs)
    assert client.get(result["rapport_url"]).status_code == 200


def test_suivi_mounted(client):
    assert client.get("/suivi/").status_code == 200
    assert client.get("/suivi/api/meta").json()["source"]["mode"] == "demo"


def test_fabric_status(client):
    status = client.get("/api/fabric").json()
    assert status["mode"] == "mock" and status["client"] == "mssql-python"
    bad = client.post("/api/fabric/connect", json={"server": "", "user": "x"})
    assert bad.status_code == 400
