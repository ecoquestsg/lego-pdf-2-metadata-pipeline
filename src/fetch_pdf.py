import hashlib
import sys
import os
import json
import requests
from urllib.parse import urlparse
from datetime import datetime, timezone
from storage import write_bytes, write_json

# constants
from config import (RAW_DIR, ENRICHED_DIR,)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_pdf_response(resp: requests.Response) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/pdf" in ctype or resp.content[:4] == b"%PDF"


def fetch_pdf(url: str) -> bytes:
    # Use a browser-ish UA because some gov sites block default python UA
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; lego-pipeline/1.0)"
    }
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()

    if not is_pdf_response(resp):
        raise ValueError(
            f"URL did not return a PDF. Content-Type={resp.headers.get('Content-Type')}"
        )
    return resp.content

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def main():
    if len(sys.argv) != 2:
        print("Usage: python src/fetch_pdf.py <pdf_url>")
        sys.exit(1)

    url = sys.argv[1].strip()
    pdf_bytes = fetch_pdf(url)

    doc_id = sha256_hex(pdf_bytes)

    pdf_path = os.path.join(RAW_DIR, f"{doc_id}.pdf")
    receipt_path = os.path.join(ENRICHED_DIR, doc_id, "receipt.json")

    write_bytes(pdf_path, pdf_bytes, content_type="application/pdf")

    receipt = {
        "doc_id": doc_id,
        "source_url": url,
        "retrieved_at": now_iso(),
        "pdf_path": pdf_path,
    }
    write_json(receipt_path, receipt)

    print("OK")
    print(f"doc_id: {doc_id}")
    print(f"source_url: {url}")
    print(f"pdf_path: {pdf_path}")
    print(f"receipt_path: {receipt_path}")


if __name__ == "__main__":
    main()
