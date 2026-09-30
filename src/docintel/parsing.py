import io
from dataclasses import dataclass, field
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
import pypdfium2 as pdfium
import pytesseract

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 5
MAX_PIXELS = 20_000_000
class InputError(ValueError):
    pass
@dataclass
class Page:
    number: int
    text: str
    image: Image.Image
    route: str
    ocr_confidence: float | None = None
    words: list[dict] = field(default_factory=list)

def validate_file(name: str, data: bytes):
    if not data or len(data) > MAX_BYTES:
        raise InputError("File must contain 1 byte to 10 MiB")
    suffix = Path(name).suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise InputError("Only PDF, PNG and JPEG are supported")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise InputError("PDF signature does not match extension")
        return suffix
    try:
        with Image.open(io.BytesIO(data)) as image:
            expected = "PNG" if suffix == ".png" else "JPEG"
            if image.format != expected or image.width * image.height > MAX_PIXELS:
                raise InputError("Image format mismatch or more than 20 million pixels")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InputError("Invalid image") from exc
    return suffix

def ocr_page(number, image, warnings):
    try:
        result = pytesseract.image_to_data(image, config="--psm 6", timeout=30, output_type=pytesseract.Output.DICT)
        lines, words, scores = {}, [], []
        for i, token in enumerate(result["text"]):
            score = float(result["conf"][i])
            if not token.strip() or score < 0:
                continue
            key = (result["block_num"][i], result["par_num"][i], result["line_num"][i])
            lines.setdefault(key, []).append(token)
            words.append({"text": token, "bbox": [result["left"][i], result["top"][i], result["left"][i] + result["width"][i], result["top"][i] + result["height"][i]]})
            scores.append(score / 100)
        return Page(number, "\n".join(" ".join(v) for v in lines.values()), image, "ocr", sum(scores)/len(scores) if scores else 0, words)
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, RuntimeError) as exc:
        warnings.append(f"Page {number}: OCR unavailable ({type(exc).__name__}); vision-only page")
        return Page(number, "", image, "vision_only")

def parse_document(name: str, data: bytes):
    suffix = validate_file(name, data)
    warnings, pages = [], []
    if suffix != ".pdf":
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1600, 1600))
        return [ocr_page(1, image, warnings)], warnings
    document = None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise InputError("Encrypted PDFs are unsupported")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise InputError("PDF must have 1 to 5 pages")
        document = pdfium.PdfDocument(data)
        for i, source in enumerate(reader.pages):
            text = source.extract_text() or ""
            rendered = document[i]
            try:
                scale = min(1.8, 1600 / max(rendered.get_size()))
                bitmap = rendered.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert("RGB").copy()
                finally:
                    bitmap.close()
            finally:
                rendered.close()
            if len(text.strip()) >= 40:
                pages.append(Page(i+1, text, image, "native_text"))
            else:
                pages.append(ocr_page(i+1, image, warnings))
        return pages, warnings
    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"PDF could not be parsed: {type(exc).__name__}") from exc
    finally:
        if document is not None:
            document.close()
