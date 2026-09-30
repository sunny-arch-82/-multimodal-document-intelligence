import json
import re
from decimal import Decimal, InvalidOperation
from typing import Protocol
from .schemas import Candidate, Fields, EvidenceRequest, LineItem

LABELS = {"vendor": "Vendor", "customer": "Customer", "document_number": "Document number", "document_date": "Date", "currency": "Currency", "subtotal": "Subtotal", "tax": "Tax", "total": "Total"}
NUMERIC = {"subtotal", "tax", "total"}
def normalize(value):
    return " ".join(str(value).casefold().split())
def money(value):
    return Decimal(str(value).replace(",", "").strip())
def classify(text):
    lowered = text.casefold()
    if "credit note" in lowered:
        return "credit_note"
    if "invoice" in lowered:
        return "invoice"
    if "supporting attachment" in lowered:
        return "supporting_attachment"
    return "unknown"
class Extractor(Protocol):
    def extract(self, pages) -> tuple[Candidate, list[str]]: ...
class RulesExtractor:
    """Transparent template baseline; not a VLM."""
    def extract(self, pages):
        values, evidence, warnings, items = {}, [], [], []
        kind = classify("\n".join(p.text for p in pages))
        for page in pages:
            for line in page.text.splitlines():
                for key, label in LABELS.items():
                    match = re.match(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", line, re.I)
                    if not match:
                        continue
                    value = match.group(1)
                    if key in values and normalize(values[key]) != normalize(value):
                        warnings.append(f"Conflicting values: {key}")
                    if key not in values:
                        values[key] = value
                        evidence.append(EvidenceRequest(field_path=key, page=page.number, quote=line.strip()))
                # Explicit rows: Item: description | quantity | unit price | amount.
                if re.match(r"^\s*Item\s*:", line, re.I):
                    cells = re.split(r"\s*\|\s*", line.split(":", 1)[1].strip())
                    try:
                        if len(cells) != 4:
                            raise ValueError("Expected four cells")
                        item = LineItem(description=cells[0], quantity=money(cells[1]), unit_price=money(cells[2]), amount=money(cells[3]))
                        index = len(items)
                        items.append(item)
                        for name in ("description", "quantity", "unit_price", "amount"):
                            evidence.append(EvidenceRequest(field_path=f"line_items.{index}.{name}", page=page.number, quote=line.strip()))
                    except (ValueError, InvalidOperation) as exc:
                        warnings.append(f"Malformed table row on page {page.number}: {type(exc).__name__}")
        for key in NUMERIC & values.keys():
            values[key] = money(values[key])
        return Candidate(document_type=kind, extracted_fields=Fields(**values, line_items=items), evidence=evidence), warnings

def parse_model_json(text):
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    elif stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
    # Reject trailing prose, duplicate keys and non-JSON numbers.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate model key: {key}")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")
    value = json.loads(stripped, object_pairs_hook=unique, parse_constant=invalid_constant)
    return Candidate.model_validate(value)
