import os
import sys
import tempfile
from pathlib import Path

import pytest

# Environnement isolé : données temporaires et mode démo forcé (aucune donnée réelle).
_TMP = tempfile.mkdtemp(prefix="merlin-tests-")
os.environ["MERLIN_DATA_DIR"] = _TMP
os.environ["MERLIN_DATA_MODE"] = "mock"
os.environ["MERLIN_SEED_DEMO_HISTORY"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from merlin.main import app

    with TestClient(app) as test_client:
        yield test_client
