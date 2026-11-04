"""Rapprochement calibré « même question ? » (merlin/match) et installation des modèles malgré le proxy."""
import hashlib
import os
from pathlib import Path

import numpy as np
import pytest

from merlin.match.gbdt import CalibratedModel, metrics
from merlin.match.matcher import key, numbers


def test_keys_and_periods():
    assert key("Q12 Describe the ESG policy.") == key("describe the esg policy") == key("1.2.3 Describe the ESG policy")
    assert key("1-year performance") != key("3-year performance")  # « 1- » n'est pas une numérotation
    assert numbers("Return over the last 12 months") == numbers("Performance sur un an") == numbers("Rendimiento a 1 año")
    assert numbers("Performance 3 ans") == numbers("Return over 36 months") != numbers("Performance 1 an")


def test_calibrated_boosting_is_calibrated_and_learns_interactions():
    rng = np.random.default_rng(0)
    n = 3000
    X = rng.random((n, 4))
    X[rng.random(n) < 0.2, 1] = np.nan  # modèle absent : valeur manquante
    same = (X[:, 0] > 0.6) & (X[:, 2] < 0.5)  # « sens proche MAIS pas de conflit de nombres »
    y = np.where(rng.random(n) < 0.9, same, ~same).astype(float)
    m = CalibratedModel(["a", "b", "c", "d"]).fit(X, y, rng.integers(0, 200, n))
    assert m.report["ece"] < 0.05 and m.report["auc"] > 0.85
    p = m.predict(np.array([[0.9, 0.5, 0.1, 0.5], [0.9, 0.5, 0.9, 0.5]]))
    assert p[0] > 0.75 and p[1] < 0.25
    assert metrics(np.array([0.9, 0.9, 0.1]), np.array([1.0, 1.0, 0.0]))["auc"] == 1.0


def test_matcher_on_unseen_wordings():
    from merlin.match.evaluate import run

    r = run()  # lexical seul (sans modèle) : le plancher, mesuré sur 70 formulations jamais vues
    assert r["trained"] and r["top1"] >= 0.8 and r["held_out"]["ece"] <= 0.1 and r["ms_per_question"] < 200


@pytest.mark.skipif(not os.environ.get("MERLIN_TEST_MODELS"), reason="modèles ONNX non fournis (MERLIN_TEST_MODELS=dossier)")
def test_matcher_with_fast_pack():
    from merlin.match.evaluate import run

    r = run(Path(os.environ["MERLIN_TEST_MODELS"]))
    assert r["top1"] >= 0.85 and r["held_out"]["ece"] <= 0.08 and r["held_out"]["auc"] >= 0.88


def test_same_answer_in_qvidian_search_and_rfi_completer(tmp_path):
    """La même question, collée dans la recherche Qvidian ou posée dans le compléteur : même texte Qvidian en tête."""
    from merlin.config import QvidianSettings
    from merlin.match.service import MATCHERS
    from merlin.qvidian.service import QvidianService
    from merlin.qvidian.suggest import votes

    svc = QvidianService(QvidianSettings(auth_url="https://login.example.invalid/QvidianAuthentication.asmx"), tmp_path)
    snap = svc.snapshot()
    svc.rebuild_history(snap)  # liens anciens RFI ↔ textes, puis rapprochement (synchrone ici)
    assert str(snap.path) in MATCHERS and svc.match_status()["stats"]["distinct"] > 20
    svc.search.get(snap, wait=True)
    for q in ["Who are the main shareholders of the management company?", "Business continuity arrangements"]:
        res = svc.match(q)
        assert res["ready"] and res["answers"], q
        top = res["answers"][0]["id"]
        assert svc.library_search(q)["results"][0]["id"] == top
        v = votes(snap, q)
        assert v and v[0].label.startswith(f"#{top} ")  # le compléteur propose le même texte en premier


# ------------------------------------------------------------------ installation des modèles
def _fake_spec(tmp_path, monkeypatch, payload: bytes):
    from merlin.search import neural

    spec = neural.ModelSpec("fake", "encoder", "Fictif", "org/fake",
                            {"model.onnx": neural.FileSpec("onnx/m.onnx", len(payload), hashlib.sha256(payload).hexdigest())}, "MIT")
    monkeypatch.setitem(neural.MODELS, "fake", spec)
    return spec


def test_download_falls_back_when_the_proxy_blocks_the_cdn(tmp_path, monkeypatch):
    from merlin.search.install import DownloadError, Downloads

    payload = b"onnx-fictif" * 1000
    _fake_spec(tmp_path, monkeypatch, payload)

    def blocked(url, part, size, progress, stop):
        raise DownloadError("HTTP 403 sur us.aws.cdn.hf.co", "proxy", "us.aws.cdn.hf.co", 403)

    def windows(url, part, size, progress, stop):
        part.write_bytes(payload)
        progress(len(payload))

    blocked.label, windows.label = "python", "windows"
    d = Downloads(tmp_path / "models", fetchers=[blocked, windows])
    d.start("fake")
    for _ in range(200):
        if not d.state["fake"]["running"]:
            break
        __import__("time").sleep(0.01)
    st = d.state["fake"]
    assert st["error"] is None and st["attempts"][0]["host"] == "us.aws.cdn.hf.co"
    assert (tmp_path / "models" / "fake" / "model.onnx").read_bytes() == payload


def test_corrupted_download_is_never_installed_and_error_explains(tmp_path, monkeypatch):
    from merlin.search.install import DownloadError, Downloads

    _fake_spec(tmp_path, monkeypatch, b"bon" * 100)

    def wrong(url, part, size, progress, stop):
        part.write_bytes(b"mal" * 100)

    def blocked(url, part, size, progress, stop):
        raise DownloadError("HTTP 403 sur us.aws.cdn.hf.co", "Le proxy de l'entreprise refuse us.aws.cdn.hf.co.", "us.aws.cdn.hf.co", 403)

    wrong.label, blocked.label = "python", "windows"
    d = Downloads(tmp_path / "models", fetchers=[wrong, blocked])
    d._stop.clear()
    d.state["fake"] = {"running": True, "done": 0, "attempts": []}
    d._run(__import__("merlin.search.neural", fromlist=["MODELS"]).MODELS["fake"])
    st = d.state["fake"]
    assert "proxy" in st["hint"] and st["host"] == "us.aws.cdn.hf.co" and not (tmp_path / "models" / "fake" / "model.onnx").exists()
    assert any("empreinte" in a["error"] for a in st["attempts"])


def test_manual_install_recognises_files_by_size_and_hash(tmp_path, monkeypatch):
    from merlin.search.install import Downloads

    payload = b"modele-fictif" * 500
    _fake_spec(tmp_path, monkeypatch, payload)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "model_quantized (1).onnx").write_bytes(payload)  # renommé par le navigateur
    (downloads / "autre.onnx").write_bytes(b"x" * len(payload))  # même taille, autre contenu : ignoré
    r = Downloads(tmp_path / "models").scan(downloads)
    assert r["ready"] == ["fake"] and r["ignored"] == ["autre.onnx"] or "autre.onnx" in r["ignored"]
    assert (tmp_path / "models" / "fake" / "model.onnx").read_bytes() == payload


def test_every_windows_path_is_tried_and_a_site_blocked_everywhere_is_explained(tmp_path, monkeypatch):
    from merlin.search import install
    from merlin.search.install import DownloadError, Downloads, diagnose, it_request
    from merlin.search.neural import MODELS

    _fake_spec(tmp_path, monkeypatch, b"x" * 50)
    calls = []

    def refuse(label):
        def f(url, part, size, progress, stop):
            calls.append(label)
            raise DownloadError(f"HTTP 403 sur huggingface.co", "proxy", "huggingface.co", 403)
        f.label = label
        return f

    d = Downloads(tmp_path / "models", fetchers=[refuse("python"), refuse("edge"), refuse("bits"), refuse("curl")])
    d.state["fake"] = {"running": True, "done": 0, "attempts": []}
    d._run(MODELS["fake"])
    st = d.state["fake"]
    assert calls == ["python", "edge", "bits", "curl"] and st["blocked_everywhere"] is True
    assert "toutes les connexions de ce poste" in st["error"] and "Edge" in st["hint"] and "IT" in st["hint"]
    assert diagnose([{"host": "a", "error": "HTTP 403"}, {"host": "b", "error": "HTTP 403"}]) is None  # deux sites : pas la même règle
    text = it_request(MODELS, ["e5-small", "rerank-mminilm"])
    assert "*.hf.co" in text and MODELS["e5-small"].files["model.onnx"].sha256 in text and "aucune donnée" in text.lower()
    monkeypatch.setattr(install.sys, "platform", "win32")
    monkeypatch.setattr(install.os.path, "exists", lambda p: True)  # PowerShell et curl présents hors du PATH
    assert [t.name for t in install.transports()] == ["python", "wininet", "windows", "curl"]
