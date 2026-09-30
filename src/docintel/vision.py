import os
import threading
from .extraction import parse_model_json
from .schemas import Candidate

class LocalVisionExtractor:
    """Lazy optional Hugging Face VLM; CPU float32 or CUDA float16."""
    def __init__(self):
        self.model = self.processor = None
        self.lock = threading.Lock()
    def extract(self, pages):
        with self.lock:
            return self._extract(pages)
    def _extract(self, pages):
        import torch
        from transformers import AutoProcessor, AutoModelForVision2Seq
        device = os.getenv("DOCINTEL_DEVICE", "cpu")
        if device not in {"cpu", "cuda"}:
            raise ValueError("DOCINTEL_DEVICE must be cpu or cuda")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but unavailable")
        if self.model is None:
            name = os.getenv("DOCINTEL_MODEL", "HuggingFaceTB/SmolVLM-256M-Instruct")
            self.processor = AutoProcessor.from_pretrained(name, trust_remote_code=False)
            self.model = AutoModelForVision2Seq.from_pretrained(name, torch_dtype=torch.float16 if device == "cuda" else torch.float32, trust_remote_code=False).to(device).eval()
        schema = Candidate.model_json_schema()
        import json
        prompt = ("Extract this synthetic invoice or credit note. Return exactly one JSON object matching the schema. "
                  "Use null for absent fields and [] for absent rows. Dates YYYY-MM-DD. Amounts positive, including credits. "
                  "Evidence uses field_path such as total or line_items.0.amount, 1-based page and an exact source quote. "
                  "Never invent values or quotes. Schema: " + json.dumps(schema) + "\nPage OCR/native text:\n" +
                  "\n".join(f"PAGE {p.number}: {p.text}" for p in pages))
        images = [page.image for page in pages]
        messages = [{"role": "user", "content": [{"type": "image"} for _ in images] + [{"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.processor(text=text, images=images, return_tensors="pt").to(device)
        with torch.inference_mode():
            generated = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        output = self.processor.batch_decode(generated[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return parse_model_json(output), ["Local VLM extraction is unvalidated; all local-model results require human review"]
