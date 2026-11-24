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


def test_fabric_connects_by_itself_from_the_team_file(client, tmp_path, monkeypatch):
    """Poste d'une collègue : adresse lue dans equipe.json, identifiant de la session Windows, rien à saisir.
    Un dossier copié d'un autre poste ne réutilise pas l'identifiant de son propriétaire."""
    import json

    from merlin.data import fabric_link
    from merlin.state import get_state

    state = get_state()
    monkeypatch.setattr(fabric_link, "saved", lambda _s: None)
    monkeypatch.setattr(fabric_link, "TEAM_FILE", tmp_path / "absent.json")
    assert fabric_link.auto_target(state) is None and client.get("/api/fabric").json()["known"] is False
    assert fabric_link.auto_connect(state) is False  # aucune adresse : la démo reste, rien n'est tenté

    team = tmp_path / "equipe.json"
    team.write_text(json.dumps({"server": "exemple.datawarehouse.fabric.microsoft.com", "database": "LKH_Fictif"}), encoding="utf-8")
    monkeypatch.setattr(fabric_link, "TEAM_FILE", team)
    monkeypatch.setattr(fabric_link, "windows_user", lambda: "collegue.fictive@exemple.com")
    assert fabric_link.auto_target(state) == {"server": "exemple.datawarehouse.fabric.microsoft.com", "database": "LKH_Fictif",
                                              "user": "collegue.fictive@exemple.com"}
    monkeypatch.setattr(fabric_link, "saved", lambda _s: {"server": "exemple.datawarehouse.fabric.microsoft.com", "database": "LKH_Fictif",
                                                          "user": "autre.personne@exemple.com", "os_user": "quelqu-un-d-autre"})
    assert fabric_link.auto_target(state)["user"] == "collegue.fictive@exemple.com"

    calls = []

    def fake_connect(_state, server, database, user, auto=False):
        calls.append((server, database, user, auto))
        raise fabric_link.DataError("Serveur injoignable.", "Vérifiez le VPN.")

    monkeypatch.setattr(fabric_link, "connect", fake_connect)
    assert fabric_link.auto_connect(state, background=False) is True
    assert calls == [("exemple.datawarehouse.fabric.microsoft.com", "LKH_Fictif", "collegue.fictive@exemple.com", True)]
    assert state.data.mode == "mock"  # échec : l'app reste utilisable
    fabric_link._status.clear()
    fabric_link._status["state"] = "disconnected"
