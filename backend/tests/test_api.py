import hashlib
import time

from merlin.state import get_state


def wait_for(client, run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in {"success", "error", "cancelled"}:
            return run
        time.sleep(0.3)
    raise AssertionError("le job ne s'est pas terminé")


def test_health_and_plugins(client):
    health = client.get("/api/health").json()
    assert health["data_mode"] == "mock"
    data = client.get("/api/automations").json()
    ids = {a["id"]: a for a in data["automations"]}
    assert {"aum_par_part", "top_lignes_portefeuille", "controle_encours"} <= set(ids)
    assert all(a["healthy"] for a in ids.values()), [a["problems"] for a in ids.values()]


def test_options_query(client):
    options = client.get("/api/automations/top_lignes_portefeuille/options/fonds").json()
    assert len(options) >= 10 and {"value", "label"} <= set(options[0])


def test_param_validation(client):
    response = client.post("/api/automations/top_lignes_portefeuille/run", json={"params": {}})
    assert response.status_code == 400
    assert "obligatoire" in response.json()["detail"]["message"]


def test_fabric_automation_end_to_end(client):
    fund = client.get("/api/automations/top_lignes_portefeuille/options/fonds").json()[0]["value"]
    run = client.post("/api/automations/top_lignes_portefeuille/run", json={"params": {"fonds": fund, "top_n": 5}}).json()
    done = wait_for(client, run["id"])
    assert done["status"] == "success", done
    assert done["outputs"] and done["outputs"][0]["name"].endswith(".xlsx")
    table = next(e for e in done["events"] if e["type"] == "table")
    assert len(table["rows"]) == 5
    download = client.get(f"/api/runs/{run['id']}/files/{done['outputs'][0]['name']}")
    assert download.status_code == 200 and download.content[:2] == b"PK"


def test_python_automation_end_to_end(client):
    run = client.post("/api/automations/controle_encours/run", json={"params": {"seuil": 2}}).json()
    done = wait_for(client, run["id"])
    assert done["status"] == "success", done
    assert [e["name"] for e in done["events"] if e["type"] == "step" and e["status"] == "done"] == [
        "Chargement des VL", "Analyse des variations", "Rédaction du rapport"]


def test_dashboard(client):
    data = client.get("/api/dashboard").json()
    assert data["counters"]["spells_total"] >= 1
    assert len(data["activity"]) == 14


def test_schedule_lifecycle(client):
    created = client.post("/api/schedules", json={
        "target_type": "automation", "target_id": "aum_par_part", "frequency": "weekly", "weekday": 0, "hour": 7,
    }).json()
    assert created["next_run"] and created["description"].startswith("Chaque lundi")
    assert client.patch(f"/api/schedules/{created['id']}", json={"enabled": False}).json()["next_run"] is None
    assert client.delete(f"/api/schedules/{created['id']}").json()["ok"]


def test_atelier_demo_flow(client):
    analysis = client.post("/api/atelier/demo").json()
    sheet = next(s for s in analysis["sheets"] if s["name"] == "Fund Information")
    assert sheet["header_row"] == 4
    assert sheet["key"]["column"] == "A" and sheet["key"]["key_type"] == "isin_part"
    proposed = {c["letter"]: c["proposed"] for c in sheet["columns"] if c["proposed"]}
    assert proposed.get("B") == "aum.nom_part"
    assert proposed.get("D") == "aum.actif_net_part_eur"

    folder = get_state().store.workbook_dir(analysis["id"])
    original = next(folder.glob("original.*"))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()

    recipe = {
        "name": "Test démo", "workbook_id": analysis["id"], "sheet": sheet["name"], "header_row": 4,
        "key_column": "A", "key_type": "isin_part",
        "mappings": [{"column": k, "extraction": v} for k, v in proposed.items()],
    }
    preview = client.post("/api/atelier/preview", json=recipe).json()
    assert preview["stats"]["fill"] > 0
    assert preview["stats"]["unchanged"] > 0  # noms déjà présents dans la démo

    run = client.post("/api/atelier/run", json=recipe).json()
    done = wait_for(client, run["id"])
    assert done["status"] == "success", done
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest  # original intact
    versions = client.get(f"/api/atelier/workbooks/{analysis['id']}").json()["versions"]
    assert len(versions) == 1 and versions[0]["written"] == preview["stats"]["fill"]

    saved = client.post("/api/atelier/recipes", json=recipe).json()
    assert saved["id"].startswith("rc_")
    assert any(r["id"] == saved["id"] for r in client.get("/api/atelier/recipes").json())


def test_suggestion(client):
    response = client.post("/api/suggestions", json={"title": "Remplir le DDQ AFG", "urgency": "vital"},
                           headers={"X-Merlin-User": "Viviane%20L."})
    assert response.json()["user"] == "Viviane L."
