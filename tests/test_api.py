from fastapi.testclient import TestClient
from docintel.api import app

def test_health_and_invalid_upload():
    client=TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.post("/documents",files={"document":("bad.txt",b"x")}).status_code == 422
    assert client.get("/documents/not-an-id").status_code == 404
