import re
from decimal import Decimal
from .extraction import normalize, money
from .schemas import Check, Evidence
REQUIRED = ("vendor", "document_number", "document_date", "currency", "subtotal", "tax", "total")
TOLERANCE = Decimal("0.02")
def field_value(fields, path):
    if path in REQUIRED or path == "customer":
        return getattr(fields, path)
    match = re.fullmatch(r"line_items\.(\d+)\.(description|quantity|unit_price|amount)", path)
    if match and int(match[1]) < len(fields.line_items):
        return getattr(fields.line_items[int(match[1])], match[2])
    return None

def supported(value, quote):
    if value is None:
        return False
    if isinstance(value, Decimal):
        for token in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w.])", quote):
            try:
                if money(token) == value:
                    return True
            except Exception:
                pass
        return False
    return normalize(value) in normalize(quote)

def ground(candidate, pages):
    grounded = []
    page_map = {page.number: page for page in pages}
    for item in candidate.evidence:
        page = page_map.get(item.page)
        found = page is not None and normalize(item.quote) in normalize(page.text)
        value_ok = found and supported(field_value(candidate.extracted_fields, item.field_path), item.quote)
        bbox = None
        if found and page.words:
            # Union of OCR words on matching quote; approximate and may include repeated tokens.
            tokens = set(normalize(item.quote).split())
            boxes = [w["bbox"] for w in page.words if normalize(w["text"]) in tokens]
            if boxes:
                bbox = [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]
        grounded.append(Evidence(**item.model_dump(), grounded=found, value_supported=bool(value_ok), bbox=bbox, coordinates="rendered_image_pixels_approximate" if bbox else None))
    return grounded

def validate(candidate, evidence, pages, warnings):
    fields, checks = candidate.extracted_fields, []
    def check(code, passed, detail):
        checks.append(Check(code=code, passed=bool(passed), detail=detail))
    check("document_type", candidate.document_type in {"invoice", "credit_note"}, "Only invoices and credit notes are extractable billing documents")
    for name in REQUIRED:
        value = getattr(fields, name)
        check("required."+name, value is not None and (not isinstance(value, str) or bool(value.strip())), "Required billing field")
    check("table.present", bool(fields.line_items), "At least one structured line item required")
    if all(getattr(fields, name) is not None for name in ("subtotal", "tax", "total")):
        check("totals.reconcile", abs(fields.subtotal + fields.tax - fields.total) <= TOLERANCE, "subtotal + tax = total within 0.02")
    if fields.subtotal is not None and fields.line_items:
        check("table.reconcile", abs(sum((i.amount for i in fields.line_items), Decimal(0)) - fields.subtotal) <= TOLERANCE, "Line amounts sum to subtotal within 0.02")
    for i, item in enumerate(fields.line_items):
        check(f"table.row.{i}", abs(item.quantity * item.unit_price - item.amount) <= TOLERANCE, "Quantity × price = amount within 0.02")
    paths = list(REQUIRED) + [f"line_items.{i}.{name}" for i in range(len(fields.line_items)) for name in ("description", "quantity", "unit_price", "amount")]
    for path in paths:
        check("evidence."+path, any(e.field_path == path and e.grounded and e.value_supported for e in evidence), "Exact quote exists on source page and supports value; not semantic proof")
    check("evidence.valid", all(e.grounded and e.value_supported for e in evidence), "Every supplied evidence reference is valid")
    for page in pages:
        check(f"page.{page.number}.quality", page.route != "vision_only" and (page.ocr_confidence is None or page.ocr_confidence >= 0.65), "Readable text and mean OCR word confidence >= 0.65")
    check("warnings", not warnings, "Conflicts, parsing/model errors and uncertain processing require review")
    quality = round(sum(c.passed for c in checks) / len(checks), 3)
    return checks, quality, any(not c.passed for c in checks)
