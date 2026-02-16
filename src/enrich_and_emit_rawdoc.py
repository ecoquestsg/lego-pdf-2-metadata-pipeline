import json
import re
import sys
import os
import time
import vertexai
from datetime import datetime, timezone
from storage import read_text, read_json, write_json
from vertexai.generative_models import GenerativeModel, GenerationConfig

# constants
from config import (
    PROJECT_ID,
    VERTEX_LOCATION,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_RESPONSE_MIME_TYPE,
    EXTRACTED_DIR,
    ENRICHED_DIR,
    RAWDOC_DIR,
)

# Hardcoded classification - edit when needed
ALLOWED_TYPE = [
    "Circulars & notices",
    "Codes",
    "Guidelines",
    "Regulations",
    "Laws",
    "Licenses & permits",
    "Reporting requirements",
    "Standards",
    "Enforcement actions"
    "Others",
]

# Hardcoded classification - edit when needed
ALLOWED_STATUS = [
    "In force",
    "Draft",
    "Consultation",
    "Superseded",
    "Unknown",
]

def clean_text(t: str) -> str:
    # Removes smart-quote mojibake from extraction pipelines
    replacements = {
        "â€œ": '"', "â€": '"',
        "â€˜": "'", "â€™": "'",
        "â€“": "-", "â€”": "-",
        "â€¦": "...",
        "Â ": " ",
    }
    for k, v in replacements.items():
        t = t.replace(k, v)
    return t


def coerce_date(d: str | None) -> str | None:
    if not d:
        return None
    d = d.strip()
    # Accept YYYY-MM-DD only
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return d
    return None


def validate_enum(v: str | None, allowed: list[str]) -> str | None:
    if not v:
        return None
    v = v.strip()
    return v if v in allowed else None

def extract_json_object(text: str) -> str:
    """
    Extract JSON object from model output.
    Handles ```json fences and extra surrounding text.
    """
    if not text:
        raise ValueError("Empty model response")

    t = text.strip()

    # Strip markdown fences if present
    t = re.sub(r"^\s*```json\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*```\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)

    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object boundaries found. Head={t[:200]!r}")

    return t[start:end+1]

def repair_json_with_model(model: GenerativeModel, bad_json: str) -> str:
    repair_prompt = (
        "You are a JSON fixer.\n"
        "Fix the following JSON so that it is strictly valid JSON.\n"
        "Return ONLY the corrected JSON object. No markdown. No explanation.\n\n"
        f"{bad_json}"
    )

    resp = model.generate_content(
        repair_prompt,
        generation_config=GenerationConfig(
            temperature=0.0,
            max_output_tokens=2048,
            response_mime_type=GEMINI_RESPONSE_MIME_TYPE,
        ),
    )
    return extract_json_object((resp.text or "").strip())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


PROMPT_TEMPLATE = """You are extracting metadata from a Singapore regulatory PDF text.
Return ONLY valid JSON. Do not include markdown. Do not include trailing commas.

Rules:
- Do NOT guess. If unknown, use null.
- Use evidence: for each non-null of title/agency/publication_date/type/status, provide at least 1 evidence item with a direct quote.
- publication_date must be in YYYY-MM-DD format or null.
- type must be one of: {allowed_type}
- status must be one of: {allowed_status}
- url must be exactly the provided source_url (do not modify it).
- topic: choose up to 3 short topics (strings). If unsure, [].

JSON schema:
{{
  "title": {{"value": string|null, "evidence": [{{"quote": string}}], "confidence": number}},
  "agency": {{"value": string|null, "evidence": [{{"quote": string}}], "confidence": number}},
  "publication_date": {{"value": string|null, "evidence": [{{"quote": string}}], "confidence": number}},
  "type": {{"value": string|null, "evidence": [{{"quote": string}}], "confidence": number}},
  "status": {{"value": string|null, "evidence": [{{"quote": string}}], "confidence": number}},
  "url": string,
  "topic": [string]
}}

source_url: {source_url}

Document text (may be partial):
\"\"\"{text}\"\"\"
"""


def main():
    if len(sys.argv) != 3:
        print("Usage: python src/enrich_and_emit_rawdoc.py <doc_id> <source_url>")
        sys.exit(1)

    doc_id = sys.argv[1].strip()
    source_url = sys.argv[2].strip()

    # Load extracted full text
    fulltext_path = os.path.join(EXTRACTED_DIR, doc_id, "fulltext.txt")
    fulltext = clean_text(read_text(fulltext_path))

    receipt_path = os.path.join(ENRICHED_DIR, doc_id, "receipt.json")
    receipt = read_json(receipt_path)
    retrieved_at = receipt.get("retrieved_at")


    # Give the model the whole thing (small here). For big docs, you'd pass first N chars.
    if len(fulltext) <= 40000:
        text_for_model = fulltext
    else:
        # Large-doc mode: only first chunk (usually contains title/date/agency)
        text_for_model = fulltext[:12000]


    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    model = GenerativeModel(GEMINI_MODEL)

    prompt = PROMPT_TEMPLATE.format(
        allowed_type=ALLOWED_TYPE,
        allowed_status=ALLOWED_STATUS,
        source_url=source_url,
        text=text_for_model,
    )

    # resp = model.generate_content(
    #     prompt,
    #     generation_config=GenerationConfig(
    #         temperature=GEMINI_TEMPERATURE,
    #         max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
    #         response_mime_type=GEMINI_RESPONSE_MIME_TYPE,
    #     ),
    # )

    # raw = resp.text.strip()

    # # Parse JSON strictly
    # try:
    #     meta = json.loads(raw)
    # except json.JSONDecodeError as e:
    #     raise RuntimeError(f"Model did not return valid JSON. Error: {e}\nRaw:\n{raw}")

    last_err = None
    raw = None

    for attempt in range(1, 3):  # 2 tries
        resp = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
                response_mime_type=GEMINI_RESPONSE_MIME_TYPE,
            ),
        )

        raw = (resp.text or "").strip()

        try:
            json_str = extract_json_object(raw)
            try:
                meta = json.loads(json_str)
            except json.JSONDecodeError:
                # Attempt a single repair pass using the model
                repaired = repair_json_with_model(model, json_str)
                meta = json.loads(repaired)

            last_err = None
            break
        except Exception as e:
            last_err = e
            time.sleep(0.6)


    if last_err is not None:
        raise RuntimeError(
            f"Model did not return valid JSON after retries. Error: {last_err}\nRaw:\n{raw}"
        )


    # Deterministic validation/normalization
    pub_date = coerce_date(meta.get("publication_date", {}).get("value"))
    doc_type = validate_enum(meta.get("type", {}).get("value"), ALLOWED_TYPE) or "Other"
    status = validate_enum(meta.get("status", {}).get("value"), ALLOWED_STATUS) or "Unknown"

    # Save metadata.json (enriched)
    enriched_obj = {
        "doc_id": doc_id,
        "source_url": source_url,
        "generated_at": now_iso(),
        "metadata": meta,
        "normalized": {
            "publication_date": pub_date,
            "type": doc_type,
            "status": status,
            "topic": meta.get("topic") or [],
        },
    }

    meta_path = os.path.join(ENRICHED_DIR, doc_id, "metadata.json")
    meta_uri = write_json(meta_path, enriched_obj)


    # Emit final portable raw-doc object (full text embedded)
    rawdoc_obj = {
        "doc_id": doc_id,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "metadata": {
            "title": meta.get("title", {}).get("value"),
            "agency": meta.get("agency", {}).get("value"),
            "publication_date": pub_date,
            "type": doc_type,
            "status": status,
            "topic": meta.get("topic") or [],
        },
        "content": {
            "full_text": fulltext
        },
        "provenance": {
            "extract_method": "document_ai",
            "fulltext_path": fulltext_path,
        },
    }

    # rawdoc_uri = gcs_write_json(RAWDOC_BUCKET, f"{doc_id}.json", rawdoc_obj)

    def slugify(s: str) -> str:
        import re
        s = (s or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        return (s[:120] or "untitled")

    # 1) Canonical (...)
    rawdoc_canonical_path = os.path.join(RAWDOC_DIR, "by-doc-id", f"{doc_id}.json")
    rawdoc_uri = write_json(rawdoc_canonical_path, rawdoc_obj)

    # 2) Alias (...)
    safe_title = slugify(rawdoc_obj["metadata"]["title"])
    rawdoc_alias_path = os.path.join(RAWDOC_DIR, "by-title", f"{safe_title}__{doc_id[:8]}.json")
    rawdoc_alias_uri = write_json(rawdoc_alias_path, rawdoc_obj)



    print("OK")
    print(f"metadata_uri: {meta_uri}")
    print(f"rawdoc_uri: {rawdoc_uri}")
    print(f"rawdoc_alias_uri: {rawdoc_alias_uri}")
    print("extracted_title:", rawdoc_obj["metadata"]["title"])
    print("extracted_agency:", rawdoc_obj["metadata"]["agency"])
    print("publication_date:", rawdoc_obj["metadata"]["publication_date"])
    print("type:", rawdoc_obj["metadata"]["type"])
    print("status:", rawdoc_obj["metadata"]["status"])
    print("topic:", rawdoc_obj["metadata"]["topic"])


if __name__ == "__main__":
    main()
