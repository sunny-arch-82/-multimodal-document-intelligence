import os
import re
import threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from .parsing import InputError, MAX_BYTES
from .pipeline import process
from .schemas import DocumentResult

app = FastAPI(title="DocIntel", version="0.1.0", description="Local synthetic billing-document extraction. Upload in /docs; inspect JSON and page evidence. No authentication: bind to localhost.")
output_dir = Path(os.getenv("DOCINTEL_OUTPUT_DIR", "outputs"))
processing_lock = threading.Lock()
@app.get("/health")
def health():
    return {"status": "ok", "backend": os.getenv("DOCINTEL_BACKEND", "rules"), "models_loaded_by_health": False}
@app.post("/documents", response_model=DocumentResult)
def upload(document: UploadFile = File(...)):
    data = document.file.read(MAX_BYTES + 1)
    backend = os.getenv("DOCINTEL_BACKEND", "rules")
    if not processing_lock.acquire(blocking=False):
        raise HTTPException(429, "Another document is processing")
    try:
        return process(document.filename or "", data, backend, output_dir)
    except (InputError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        processing_lock.release()
        document.file.close()

def artifact(document_id, filename):
    if not re.fullmatch(r"[a-f0-9]{64}", document_id):
        raise HTTPException(404, "Unknown document")
    path = output_dir / document_id / filename
    if not path.is_file():
        raise HTTPException(404, "Unknown artifact")
    return path
@app.get("/documents/{document_id}", response_model=DocumentResult)
def get_result(document_id: str):
    return DocumentResult.model_validate_json(artifact(document_id, "result.json").read_text())
@app.get("/documents/{document_id}/pages/{page}")
def get_page(document_id: str, page: int):
    if not 1 <= page <= 5:
        raise HTTPException(404, "Unknown page")
    return FileResponse(artifact(document_id, f"page-{page}.png"), media_type="image/png")
