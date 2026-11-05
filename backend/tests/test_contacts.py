"""Qui contacter : inventaire des questions posées aux autres équipes, à partir de mails fictifs (lecture d'Outlook
simulée : mêmes champs que le lecteur Windows)."""
import io

from openpyxl import load_workbook

from merlin.contacts.extract import frame, questions
from merlin.contacts.inventory import Inventory, asks_from_mails, dd_type

RFP = {"name": "AmeuRFPteam", "email": "ameurfpteam@exemple-fictif.test", "department": "", "list": True}
ALICE = {"name": "Alice Fictive", "email": "alice@exemple-fictif.test", "department": "RFP", "list": False}
BOB = {"name": "Bob Imaginaire", "email": "bob@exemple-fictif.test", "department": "Conformité", "list": False}
CHLOE = {"name": "Chloé Inventée", "email": "chloe@exemple-fictif.test", "department": "Risques", "list": False}
CLIENT = {"name": "Client", "email": "contact@client-fictif.test", "department": "", "list": False}


def mail(i, subject, to, body, sender=ALICE, date="2026-03-01"):
    return {"id": str(i), "subject": subject, "date": date, "sender": sender, "to": to, "cc": [RFP], "attachments": [],
            "questions": questions(body), "frame": frame(body)}


BODY_BOB = """Bonjour Bob,

Dans le cadre de la due diligence de l'assureur, pourriez-vous nous indiquer :
- le nombre de collaborateurs de la conformité
- la date du dernier contrôle de l'AMF

Merci d'avance,
Alice"""


def mails():
    return [
        mail(1, "DD Mutuelle Fictive - questions conformité", [BOB], BODY_BOB),
        mail(2, "Questionnaire ESG - Caisse Fictive", [CHLOE], "Bonjour Chloé,\n\nAvez-vous une politique d'exclusion du charbon ?\nQuel est le score SFDR du fonds ?\n\nMerci d'avance,"),
        mail(3, "RE: DD Consultant Mercer", [BOB], "Bonjour Bob,\n\nDans le cadre de la due diligence, pourriez-vous nous indiquer :\n- Nombre de collaborateurs de la conformité ?\n\nMerci d'avance,", date="2026-06-01"),
        mail(4, "RE: questions", [ALICE], "Bonjour,\n\nVoici nos réponses : 12 personnes ?\n", sender=BOB),  # réponse : jamais lue
        mail(5, "Envoi au client", [CLIENT], "Bonjour,\n\nPouvez-vous nous confirmer la date de la réunion ?\n"),  # vers le client
    ]


def test_questions_and_frame_from_a_mail():
    assert questions(BODY_BOB) == ["le nombre de collaborateurs de la conformité", "la date du dernier contrôle de l'AMF"]
    f = frame(BODY_BOB)
    assert f["greeting"] == "Bonjour Bob," and f["intro"].endswith(":") and f["closing"].startswith("Merci")
    assert dd_type("DD Consultant Mercer")[0] == "consultant" and dd_type("Questionnaire ESG")[0] == "esg_ops"


def test_inventory_who_to_contact(tmp_path):
    asks, stats = asks_from_mails(mails(), "AmeuRFPteam", {ALICE["email"]})
    assert stats["vers_client"] == 1 and stats["sans_demande"] == 1  # le client et la réponse de Bob sont ignorés
    inv = Inventory(tmp_path / "inventory.json")
    inv.rebuild(asks, stats)
    groups = {g["question"]: g for g in inv.data["groups"]}
    staff = next(g for g in groups.values() if "collaborateurs" in g["question"].lower())
    assert staff["times"] == 2 and staff["team"] == "Conformité" and "Bob Imaginaire" in staff["people"][0]
    assert set(staff["dd_types"]) == {"Institutionnel", "Consultant"}
    assert any(g["team"] == "Risques" and "ESG / opérationnelle" in g["dd_types"] for g in groups.values())

    plan = inv.ask_plan(["Combien de collaborateurs dans l'équipe conformité ?", "Question jamais posée sur la météo"],
                        client="Caisse Fictive", fund="Fonds Imaginaire", deadline="15/11")
    team = plan["teams"][0]
    assert team["team"] == "Conformité" and team["to"] == "bob@exemple-fictif.test"
    assert team["mail"].startswith("Bonjour") and "1. Combien de collaborateurs" in team["mail"] and "15/11" in team["mail"]
    assert plan["unknown"] == ["Question jamais posée sur la météo"]

    wb = load_workbook(io.BytesIO(inv.to_excel()))
    assert wb.sheetnames == ["Questions", "Par équipe", "Par type de due diligence", "Mails types"]
    ws = wb["Questions"]
    head = [c.value for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        if "AMF" in row[0].value:
            row[head.index("Équipe (corrigée)")].value = "Contrôle interne"
    buf = io.BytesIO()
    wb.save(buf)
    assert inv.import_corrections(buf.getvalue()) == 1
    assert next(g for g in inv.data["groups"] if "AMF" in g["question"])["team"] == "Contrôle interne"
    inv.rebuild(asks, stats)  # nouvelle lecture d'Outlook : la correction reste
    assert next(g for g in inv.data["groups"] if "AMF" in g["question"])["team"] == "Contrôle interne"


def test_api_without_outlook(client):
    st = client.get("/api/contacts").json()
    assert st["outlook"] is False and st["team"] == "AmeuRFPteam"
    assert client.post("/api/contacts/ask", json={"questions": ["x ?"]}).json()["unknown"] == ["x ?"]


def _collector():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "outils" / "collecte_qui_contacter" / "collecte.py"
    spec = importlib.util.spec_from_file_location("collecte", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


def test_collector_extraction_is_an_exact_copy_of_the_app():
    from pathlib import Path

    _, path = _collector()
    app = (Path(__file__).resolve().parents[1] / "merlin" / "contacts" / "extract.py").read_text(encoding="utf-8")
    copy = path.read_text(encoding="utf-8")
    block = app[app.index("import re\n"):app.index("def excel_questions(")].rstrip()
    assert block in copy, "outils/collecte_qui_contacter/collecte.py : recopier la partie extraction de merlin/contacts/extract.py"


def test_collected_file_from_a_colleague_is_merged(tmp_path, monkeypatch):
    mod, _ = _collector()
    monkeypatch.setattr(mod, "DESTINATION", str(tmp_path / "SharePoint - Glossaire"))
    monkeypatch.setenv("USERNAME", "collegue.fictive")
    collected = [{**m, "id": f"c{m['id']}"} for m in mails()]
    target = mod.write(collected, [ALICE["email"]], 36)
    assert target.parent.name == "Collectes" and target.parent.parent.name == "SharePoint - Glossaire" and "collegue.fictive" in target.name
    inv = Inventory(tmp_path / "contacts" / "inventory.json")
    got = inv.import_collected(target.read_bytes())
    assert got == {"by": "collegue.fictive", "mails": 5}
    inv.save_source("ma_boite", {"by": "moi", "team": "AmeuRFPteam", "members": [ALICE["email"]], "mails": mails()[:2]})
    summary = inv.rebuild_all("AmeuRFPteam")
    assert {x["by"] for x in summary["sources"]} == {"moi", "collegue.fictive"} and summary["teams"].get("Conformité")
    assert inv.import_collected(inv.to_excel()) is None  # un fichier exporté n'est pas une collecte


def test_the_bat_contains_the_current_collector():
    """Un seul fichier à copier : le .bat embarque collecte.py (reconstruire avec construire.py après modification)."""
    _, path = _collector()
    bat = path.with_name("Collecte_Qui_Contacter.bat").read_text(encoding="utf-8").replace("\r\n", "\n")
    marker = "#" + "__PYTHON__"
    assert bat.count(marker) == 1, "le marqueur ne doit apparaître qu'une fois"
    assert bat.split(marker, 1)[1].lstrip() == path.read_text(encoding="utf-8"), "lancer : python outils/collecte_qui_contacter/collecte.py --construire"
    head = bat.split(marker, 1)[0]
    assert "COLLECTE_DIR" in head and head.rstrip().endswith("exit /b 1")  # rien n'est exécuté après le marqueur


def test_collector_builds_the_glossary_itself_and_keeps_corrections(tmp_path, monkeypatch):
    from openpyxl import load_workbook

    mod, _ = _collector()
    folder = tmp_path / "Glossaire .PY"
    monkeypatch.setattr(mod, "DESTINATION", str(folder))
    for user, ms in (("collegue.a", mails()), ("collegue.b", [{**m, "id": "b" + m["id"]} for m in mails()[:1]])):
        monkeypatch.setenv("USERNAME", user)
        mod.write(ms, [ALICE["email"]], 36)
    master, n, sources = mod.build_glossary(folder)
    assert master.name == "Glossaire qui contacter.xlsx" and sources == 2
    wb = load_workbook(master)
    assert wb.sheetnames == ["Questions", "Par équipe", "Par type de due diligence", "Mails types", "Sources"]
    ws = wb["Questions"]
    head = [c.value for c in ws[1]]
    staff = next(r for r in ws.iter_rows(min_row=2) if "collaborateurs" in r[0].value.lower())
    assert staff[head.index("Équipe")].value == "Conformité" and staff[head.index("Nb de fois")].value == 3  # 2 boîtes, fusionnées
    staff[head.index("Équipe (corrigée)")].value = "Contrôle interne"
    wb.save(master)
    mod.build_glossary(folder)  # nouveau lancement : la correction reste
    ws = load_workbook(master)["Questions"]
    assert next(r for r in ws.iter_rows(min_row=2, values_only=True) if "collaborateurs" in r[0].lower())[1] == "Contrôle interne"


def test_fast_reader_opens_only_the_team_requests():
    """Outlook simulé : le tableau (GetTable/GetArray) suffit à écarter les réponses ; seules les demandes sont ouvertes."""
    from datetime import datetime

    mod, _ = _collector()

    class Att:
        Count = 0

        def __iter__(self):
            return iter([])

    class Item:
        def __init__(self, eid, sender, body):
            self.EntryID, self.Body, self.Subject, self.SenderName, self.SenderEmailAddress = eid, body, "DD Mutuelle Fictive", sender, sender
            self.SentOn, self.Attachments, self.Recipients, self.Sender = datetime(2026, 3, 1), Att(), [], None

    rows = [("E1", ALICE["email"], ALICE["email"]), ("E2", BOB["email"], BOB["email"]), ("E3", ALICE["email"], ALICE["email"])]
    items = {"E1": Item("E1", ALICE["email"], BODY_BOB), "E2": Item("E2", BOB["email"], "Réponse : 12 ?"), "E3": Item("E3", ALICE["email"], "Merci !")}
    opened = []

    class Table:
        def __init__(self):
            self.done, self.Columns = False, type("C", (), {"RemoveAll": lambda s: None, "Add": lambda s, c: None})()

        @property
        def EndOfTable(self):
            return self.done

        def GetArray(self, n):
            self.done = True
            return rows

    class Folder:
        Name, DefaultItemType, Folders = "Boîte de réception", 0, []

        def GetTable(self, f):
            assert "AmeuRFPteam" in f and "IPM.Note" in f
            return Table()

    class NS:
        Stores = [type("S", (), {"GetRootFolder": lambda s: Folder()})()]

        def GetItemFromID(self, eid):
            opened.append(eid)
            return items[eid]

    r = mod.Reader.__new__(mod.Reader)
    r.ns, r.people = NS(), {}
    got = list(r.mails(datetime(2024, 1, 1), {ALICE["email"]}, known=set()))
    assert opened == ["E1", "E3"]  # la réponse de Bob n'est jamais ouverte
    assert [m["questions"] for m in got] == [questions(BODY_BOB)]  # E3 sans question : écarté
