"""Create original synthetic fixtures only; does not invoke DocIntel/OCR/models."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"sample"
def native(name, pages):
    c=canvas.Canvas(str(OUT/name),pagesize=(612,792))
    for lines in pages:
        c.setFont("Helvetica",11)
        for i,line in enumerate(lines): c.drawString(40,750-i*23,line)
        c.showPage()
    c.save()
def raster(lines):
    img=Image.new("RGB",(1224,1584),"white")
    try: font=ImageFont.truetype("DejaVuSans.ttf",22)
    except OSError: font=ImageFont.load_default(size=22)
    draw=ImageDraw.Draw(img)
    for i,line in enumerate(lines): draw.text((80,80+i*46),line,fill="black",font=font)
    return img

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    base=["SYNTHETIC DEMO - NO REAL TRANSACTION", "Invoice", "Vendor: Atlas Demo Supplies", "Customer: Demo Workshop", "Document number: INV-1001", "Date: 2026-09-01", "Currency: USD", "Item: Cable kit | 2 | 50.00 | 100.00", "Subtotal: 100.00", "Tax: 10.00", "Total: 110.00"]
    native("native_invoice.pdf",[base])
    scan=raster(base); scan.save(OUT/"scanned_invoice.png"); scan.save(OUT/"scanned_invoice.jpg",quality=92)
    c=canvas.Canvas(str(OUT/"scanned_invoice.pdf"),pagesize=(612,792)); c.drawImage(ImageReader(scan),0,0,width=612,height=792); c.save()
    credit=[s.replace("Invoice","Credit note").replace("INV-1001","CN-1001") for s in base]
    native("credit_note.pdf",[credit])
    table=base[:7]+[f"Item: Part {i} | 1 | 10.00 | 10.00" for i in range(1,13)]
    native("table_invoice.pdf",[table[:13], ["SYNTHETIC DEMO - CONTINUED"]+table[13:]+["Subtotal: 120.00","Tax: 12.00","Total: 132.00"]])
    native("incomplete_invoice.pdf",[[s for s in base if not s.startswith(("Date:","Currency:"))]])
    native("conflicting_invoice.pdf",[base+["Total: 210.00"]])
    native("ambiguous_attachment.pdf",[["SYNTHETIC DEMO", "Supporting attachment", "Supplier estimates pending", "No approved billing details"]])
    fields=dict(vendor="Atlas Demo Supplies",customer="Demo Workshop",document_number="INV-1001",document_date="2026-09-01",currency="USD",subtotal="100.00",tax="10.00",total="110.00")
    row=dict(description="Cable kit",quantity="2",unit_price="50.00",amount="100.00")
    examples=[]
    for name in ("native_invoice.pdf","scanned_invoice.png","scanned_invoice.jpg","scanned_invoice.pdf","credit_note.pdf","table_invoice.pdf","incomplete_invoice.pdf","conflicting_invoice.pdf","ambiguous_attachment.pdf"):
        f=fields.copy(); rows=[row.copy()]; kind="invoice"; review=False; evidence={"total":1,"vendor":1}
        if name=="credit_note.pdf": kind="credit_note"; f["document_number"]="CN-1001"
        if name=="table_invoice.pdf":
            f.update(subtotal="120.00",tax="12.00",total="132.00")
            rows=[dict(description=f"Part {i}",quantity="1",unit_price="10.00",amount="10.00") for i in range(1,13)]
            evidence["total"]=2
        if name=="incomplete_invoice.pdf": f.update(document_date=None,currency=None); review=True
        if name=="conflicting_invoice.pdf": review=True
        if name=="ambiguous_attachment.pdf": kind="supporting_attachment"; f={k:None for k in fields}; rows=[]; evidence={}; review=True
        examples.append(dict(file=name,document_type=kind,review_required=review,fields=f,line_items=rows,evidence_pages=evidence))
    (ROOT/"evals"/"manifest.json").write_text(json.dumps(examples,indent=2))
if __name__=="__main__": main()
