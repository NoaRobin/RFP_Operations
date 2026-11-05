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
