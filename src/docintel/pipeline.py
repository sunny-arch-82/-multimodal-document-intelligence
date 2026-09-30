import hashlib
import os
from pathlib import Path
from .parsing import parse_document
from .extraction import RulesExtractor, classify
from .schemas import Candidate, Fields, PageSummary, DocumentResult
from .validation import ground, validate
from .vision import LocalVisionExtractor

EXTRACTORS = {"rules": RulesExtractor(), "local_vlm": LocalVisionExtractor()}
def process(name, data, backend="rules", output_dir=None):
    if backend not in EXTRACTORS:
        raise ValueError("Backend must be rules or local_vlm")
    pages, warnings = parse_document(name, data)
    try:
        candidate, extraction_warnings = EXTRACTORS[backend].extract(pages)
        warnings.extend(extraction_warnings)
    except Exception as exc:
        # Malformed extraction is a visible review result, never a silent rules fallback.
        candidate = Candidate(document_type=classify("\n".join(p.text for p in pages)), extracted_fields=Fields())
        warnings.append(f"Extraction failed: {type(exc).__name__}: {str(exc)[:400]}")
    evidence = ground(candidate, pages)
    checks, confidence, review = validate(candidate, evidence, pages, warnings)
    # Include backend/model identity in artifact ID to avoid overwriting comparisons.
    identity = backend + (os.getenv("DOCINTEL_MODEL", "HuggingFaceTB/SmolVLM-256M-Instruct") if backend == "local_vlm" else "v1")
    document_id = hashlib.sha256(data + identity.encode()).hexdigest()
    result = DocumentResult(document_id=document_id, backend=backend, document_type=candidate.document_type, extracted_fields=candidate.extracted_fields, evidence=evidence, validation_results=checks, confidence=confidence, review_required=review, warnings=warnings, pages=[PageSummary(page=p.number, route=p.route, character_count=len(p.text), ocr_confidence=p.ocr_confidence) for p in pages])
    if output_dir is not None:
        directory = Path(output_dir) / document_id
        directory.mkdir(parents=True, exist_ok=True)
        for page in pages:
            page.image.save(directory / f"page-{page.number}.png")
        temp = directory / "result.tmp"
        temp.write_text(result.model_dump_json(indent=2))
        temp.replace(directory / "result.json")
    return result
