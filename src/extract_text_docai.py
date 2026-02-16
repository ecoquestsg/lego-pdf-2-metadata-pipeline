import json
import os
import sys
import fitz  # PyMuPDF
from google.cloud import documentai_v1 as documentai
from storage import read_bytes, write_json, write_text

# constants
from config import (
    PROJECT_ID,
    LOCATION,
    PROCESSOR_ID,
    MAX_PAGES_SYNC,
    RAW_DIR,
    EXTRACTED_DIR,
)

def extract_full_text(doc: documentai.Document) -> str:
    return doc.text or ""


def count_pdf_pages(pdf_bytes: bytes) -> int:
    d = fitz.open(stream=pdf_bytes, filetype="pdf")
    n = d.page_count
    d.close()
    return n


def split_pdf_bytes(pdf_bytes: bytes, start_page: int, end_page_exclusive: int) -> bytes:
    """
    Returns a new PDF containing pages [start_page, end_page_exclusive).
    PyMuPDF pages are 0-indexed.
    """
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    out.insert_pdf(src, from_page=start_page, to_page=end_page_exclusive - 1)
    new_bytes = out.tobytes()
    out.close()
    src.close()
    return new_bytes


def process_pdf_bytes(client, processor_name: str, pdf_bytes: bytes) -> documentai.Document:
    raw_document = documentai.RawDocument(content=pdf_bytes, mime_type="application/pdf")
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document, skip_human_review=True)
    result = client.process_document(request=request)
    return result.document


def main():
    if len(sys.argv) != 2:
        print("Usage: python src/extract_text_docai.py <doc_id>")
        sys.exit(1)

    doc_id = sys.argv[1].strip()
    pdf_path = os.path.join(RAW_DIR, f"{doc_id}.pdf")
    pdf_bytes = read_bytes(pdf_path)

    page_count = count_pdf_pages(pdf_bytes)

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{LOCATION}-documentai.googleapis.com"}
    )
    processor_name = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

    all_text_parts = []
    docai_chunks = []

    if page_count <= MAX_PAGES_SYNC:
        doc = process_pdf_bytes(client, processor_name, pdf_bytes)
        all_text_parts.append(extract_full_text(doc))
        docai_chunks.append(documentai.Document.to_dict(doc))
    else:
        # Split into 15-page chunks (0-indexed)
        for start in range(0, page_count, MAX_PAGES_SYNC):
            end = min(start + MAX_PAGES_SYNC, page_count)
            chunk_bytes = split_pdf_bytes(pdf_bytes, start, end)

            doc = process_pdf_bytes(client, processor_name, chunk_bytes)

            # Keep chunk outputs (useful for debugging/audit)
            docai_chunks.append({
                "chunk_range": {"start_page": start + 1, "end_page": end},  # 1-indexed for humans
                "document": documentai.Document.to_dict(doc),
            })
            all_text_parts.append(extract_full_text(doc))

    full_text = "\n\n".join(all_text_parts)

    # Write outputs
    docai_path = os.path.join(EXTRACTED_DIR, doc_id, "docai.json")
    fulltext_path = os.path.join(EXTRACTED_DIR, doc_id, "fulltext.txt")

    write_json(docai_path, {"page_count": page_count, "chunks": docai_chunks})
    write_text(fulltext_path, full_text, content_type="text/plain")

    print("OK")
    print(f"doc_id: {doc_id}")
    print(f"pages: {page_count}")
    print(f"docai_uri: {docai_path}")
    print(f"fulltext_uri: {fulltext_path}")
    print(f"chars_extracted: {len(full_text)}")


if __name__ == "__main__":
    main()
