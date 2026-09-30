"""Explicit opt-in evaluation. No packaged results; tiny synthetic smoke dataset."""
import json
from decimal import Decimal
from pathlib import Path
from .pipeline import process
from .extraction import normalize

def equal(actual, expected, numeric=False):
    if actual is None or expected is None:
        return actual is expected
    if numeric:
        return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal("0.02")
    return normalize(actual) == normalize(expected)

def evaluate(manifest, backend="rules"):
    manifest = Path(manifest)
    examples = json.loads(manifest.read_text())
    counts = dict(class_correct=0, review_correct=0, fields_correct=0, fields_exact=0, fields_total=0, tp=0, fp=0, fn=0, rows_correct=0, rows_total=0, evidence_correct=0, evidence_total=0, reconcile_correct=0)
    classes, results = {}, []
    for example in examples:
        path = manifest.parent.parent / "data" / "sample" / example["file"]
        result = process(path.name, path.read_bytes(), backend)
        fields = result.extracted_fields.model_dump(mode="json")
        counts["class_correct"] += result.document_type == example["document_type"]
        counts["review_correct"] += result.review_required == example["review_required"]
        for label in {example["document_type"], result.document_type}:
            c = classes.setdefault(label, dict(tp=0, fp=0, fn=0))
            c["tp"] += result.document_type == label == example["document_type"]
            c["fp"] += result.document_type == label != example["document_type"]
            c["fn"] += example["document_type"] == label != result.document_type
        for key, expected in example["fields"].items():
            actual = fields.get(key)
            correct = equal(actual, expected, key in {"subtotal", "tax", "total"})
            counts["fields_total"] += 1
            counts["fields_correct"] += correct
            counts["fields_exact"] += actual == expected
            if expected is not None and correct:
                counts["tp"] += 1
            else:
                counts["fp"] += actual is not None
                counts["fn"] += expected is not None
        expected_rows = example.get("line_items", [])
        actual_rows = fields["line_items"]
        counts["rows_total"] += max(len(expected_rows), len(actual_rows))
        for actual, expected in zip(actual_rows, expected_rows):
            counts["rows_correct"] += all(equal(actual.get(k), v, k != "description") for k, v in expected.items())
        for key, page in example.get("evidence_pages", {}).items():
            counts["evidence_total"] += 1
            counts["evidence_correct"] += any(e.field_path == key and e.page == page and e.grounded and e.value_supported for e in result.evidence)
        counts["reconcile_correct"] += any(c.code == "totals.reconcile" and c.passed for c in result.validation_results)
        results.append({"file": example["file"], "document_type": result.document_type, "review_required": result.review_required, "warnings": result.warnings})
    def ratio(a,b):
        return a/b if b else None
    def prf(c):
        p, r = ratio(c["tp"], c["tp"]+c["fp"]), ratio(c["tp"], c["tp"]+c["fn"])
        return {"precision":p, "recall":r, "f1": 2*p*r/(p+r) if p is not None and r is not None and p+r else 0}
    return {"backend":backend, "samples":len(examples), "classification_accuracy":ratio(counts["class_correct"],len(examples)), "classification_per_class":{k:prf(v) for k,v in classes.items()}, "field_exact_match":ratio(counts["fields_exact"],counts["fields_total"]), "field_normalized_or_numeric_match":ratio(counts["fields_correct"],counts["fields_total"]), "field_prf":prf(counts), "ordered_line_item_accuracy":ratio(counts["rows_correct"],counts["rows_total"]), "evidence_page_accuracy":ratio(counts["evidence_correct"],counts["evidence_total"]), "review_accuracy":ratio(counts["review_correct"],len(examples)), "reconciliation_success_rate":ratio(counts["reconcile_correct"],len(examples)), "counts":counts, "results":results, "limitations":"Synthetic template dataset only; not an enterprise quality claim. Fields scored only where annotated. OCR-dependent results require Tesseract."}
