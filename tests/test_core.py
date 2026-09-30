import io
from decimal import Decimal
import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas
from docintel.parsing import InputError, validate_file, parse_document, Page
from docintel.extraction import classify, RulesExtractor, parse_model_json
from docintel.schemas import EvidenceRequest
from docintel.validation import ground, validate
from docintel.pipeline import process, EXTRACTORS

def image():
    return Image.new("RGB", (100,100), "white")
def pdf(text):
    out=io.BytesIO(); canvas=Canvas(out)
    for i, line in enumerate(text.splitlines()):
        canvas.drawString(40,800-i*20,line)
    canvas.save(); return out.getvalue()
TEXT = "Invoice\nVendor: Demo\nDocument number: INV-1\nDate: 2026-09-01\nCurrency: USD\nSubtotal: 100.00\nTax: 10.00\nTotal: 110.00\nItem: Cable | 2 | 50.00 | 100.00"

def test_validation_rejects_mismatch_and_unsupported():
    for name, data in [("x.exe",b"x"),("x.pdf",b"bad"),("x.png",b"bad"),("x.pdf",b"")]:
        with pytest.raises(InputError): validate_file(name,data)

def test_native_routing_no_ocr(monkeypatch):
    monkeypatch.setattr("docintel.parsing.ocr_page",lambda *a: pytest.fail("Native PDF must not OCR"))
    pages,_=parse_document("x.pdf",pdf(TEXT))
    assert pages[0].route == "native_text"
    assert "INV-1" in pages[0].text

def test_classification():
    assert classify("CREDIT NOTE") == "credit_note"
    assert classify("INVOICE") == "invoice"
    assert classify("random memo") == "unknown"

def test_rules_reconcile_evidence():
    pages=[Page(1,TEXT,image(),"native_text")]
    candidate,warnings=RulesExtractor().extract(pages)
    evidence=ground(candidate,pages)
    checks,quality,review=validate(candidate,evidence,pages,warnings)
    assert not review and quality == 1
    assert candidate.extracted_fields.line_items[0].amount == Decimal("100")
    assert all(c.passed for c in checks)

def test_wrong_total_missing_and_forged_evidence():
    pages=[Page(1,TEXT,image(),"native_text")]
    candidate,_=RulesExtractor().extract(pages)
    candidate.extracted_fields.total=Decimal("999")
    candidate.extracted_fields.vendor=None
    candidate.evidence.append(EvidenceRequest(field_path="total",page=2,quote="999"))
    checks,_,review=validate(candidate,ground(candidate,pages),pages,[])
    assert review
    assert any(c.code=="totals.reconcile" and not c.passed for c in checks)

def test_malformed_model_and_schema():
    for value in ['{"document_type":"invoice","document_type":"unknown"}', "not JSON", '{"document_type":"invoice","extracted_fields":{"currency":"XYZ"}}']:
        with pytest.raises(ValueError): parse_model_json(value)

def test_conflict_and_low_ocr_review():
    pages=[Page(1,TEXT+"\nTotal: 200.00",image(),"ocr",0.2)]
    candidate,warnings=RulesExtractor().extract(pages)
    assert warnings
    assert validate(candidate,ground(candidate,pages),pages,warnings)[2]

def test_model_failure_returns_review(monkeypatch):
    class Bad:
        def extract(self,pages): raise ValueError("Malformed response")
    monkeypatch.setitem(EXTRACTORS,"local_vlm",Bad())
    result=process("x.pdf",pdf(TEXT),"local_vlm")
    assert result.review_required and "Extraction failed" in result.warnings[0]
