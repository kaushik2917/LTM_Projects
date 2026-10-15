import os
import tempfile
from pathlib import Path
import pytest

TEMP = tempfile.TemporaryDirectory(prefix='callsense-tests-')
os.environ['DATABASE_URL']='sqlite:///'+(Path(TEMP.name)/'test.db').as_posix()
os.environ['MOCK_MODE']='true'
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope='session')
def client():
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    from app.database.store import engine
    engine.dispose()
    TEMP.cleanup()
