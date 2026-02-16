import argparse
import os
import random
import subprocess
import sys
import time
import json
from typing import List, Optional, Tuple
from datetime import datetime, timezone

# constants
from config import (
    RAWDOC_DIR, 
    ENRICHED_DIR, 
    BATCH_MIN_DELAY, 
    BATCH_MAX_DELAY,
    )

RAW_DOC_CANONICAL_DIR = os.path.join(RAWDOC_DIR, "by-doc-id")
RAW_DOC_TITLE_DIR = os.path.join(RAWDOC_DIR, "by-title")


def run(cmd: List[str]) -> None:
    print("\n>>", " ".join(cmd))
    subprocess.check_call(cmd)


def run_capture(cmd: List[str]) -> str:
    print("\n>>", " ".join(cmd))
    return subprocess.check_output(cmd, text=True)


def parse_doc_id(fetch_output: str) -> Optional[str]:
    for line in fetch_output.splitlines():
        if line.startswith("doc_id:"):
            return line.split(":", 1)[1].strip()
    return None


def already_processed(doc_id: str) -> bool:
    canonical_path = os.path.join(RAW_DOC_CANONICAL_DIR, f"{doc_id}.json")
    return os.path.exists(canonical_path)


def read_urls_file(path: str) -> List[str]:
    urls: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            urls.append(line)
    return urls


def process_one_url(url: str) -> Tuple[str, bool]:
    """
    Returns (doc_id, processed)
    processed=False means it was skipped because already processed.
    """
    # 1) fetch (downloads PDF and writes receipt locally)
    out = run_capture([sys.executable, "src/fetch_pdf.py", url])
    print(out)

    doc_id = parse_doc_id(out)
    if not doc_id:
        raise RuntimeError("Could not parse doc_id from fetch output")

    # skip if we already have final rawdoc for this exact PDF hash
    if already_processed(doc_id):
        print(f"SKIP: already processed doc_id={doc_id}")
        return doc_id, False

    # 2) extract (Document AI)
    run([sys.executable, "src/extract_text_docai.py", doc_id])

    # 3) enrich + emit (Gemini + JSON outputs)
    run([sys.executable, "src/enrich_and_emit_rawdoc.py", doc_id, url])

    print("\nDONE.")
    print(f"- canonical rawdoc: {os.path.join(RAW_DOC_CANONICAL_DIR, f'{doc_id}.json')}")
    print(f"- title alias rawdoc: check lego-rawdoc-objects/by-title/ for *{doc_id[:8]}.json")

    return doc_id, True

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description="Run PDF → RawDoc pipeline (single URL or batch).")
    parser.add_argument("url", nargs="?", help="Single PDF URL to process.")
    parser.add_argument("--batch", type=str, help="Path to a text file with one URL per line.")
    parser.add_argument("--min-delay", type=float, default=BATCH_MIN_DELAY, help="Minimum delay seconds between processed URLs.")
    parser.add_argument("--max-delay", type=float, default=BATCH_MAX_DELAY, help="Maximum delay seconds between processed URLs.")
    parser.add_argument("--no-delay", action="store_true", help="Disable delay between URLs.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop batch immediately if a URL fails.")
    args = parser.parse_args()

    if not args.url and not args.batch:
        parser.error("Provide either a single <url> or --batch <urls.txt>")

    if args.min_delay < 0 or args.max_delay < 0 or args.max_delay < args.min_delay:
        parser.error("--min-delay/--max-delay must be non-negative and max >= min")

    os.makedirs(RAW_DOC_CANONICAL_DIR, exist_ok=True)
    os.makedirs(RAW_DOC_TITLE_DIR, exist_ok=True)
    os.makedirs(ENRICHED_DIR, exist_ok=True)


    urls: List[str] = []
    if args.batch:
        urls = read_urls_file(args.batch)
        if not urls:
            raise RuntimeError(f"No URLs found in batch file: {args.batch}")
    else:
        urls = [args.url.strip()]

    processed_count = 0
    skipped_count = 0
    failed_count = 0

    report = {
        "started_at": now_iso(),
        "batch_file": args.batch,
        "total_urls": len(urls),
        "processed": [],
        "skipped": [],
        "failed": [],
    }


    for i, url in enumerate(urls, start=1):
        print("\n" + "=" * 80)
        print(f"[{i}/{len(urls)}] URL: {url}")

        try:
            doc_id, processed = process_one_url(url)

            if processed:
                processed_count += 1
                report["processed"].append({"url": url, "doc_id": doc_id})
                if not args.no_delay:
                    delay = random.uniform(args.min_delay, args.max_delay)
                    print(f"\nSleeping {delay:.2f}s before next URL...")
                    time.sleep(delay)

            else:
                skipped_count += 1
                report["skipped"].append({"url": url, "doc_id": doc_id})

        except Exception as e:
            failed_count += 1
            err = f"{type(e).__name__}: {e}"
            print(f"\nERROR (continuing batch): {err}")
            report["failed"].append({"url": url, "error": err})

            if args.stop_on_error:
                print("stop-on-error enabled. Stopping batch.")
                break

    
    report["finished_at"] = now_iso()
    report_path = os.path.join(ENRICHED_DIR, "batch_report.json")

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nBatch report written to: {report_path}")


    print("\n" + "=" * 80)
    print("BATCH COMPLETE")
    print(f"processed: {processed_count}")
    print(f"skipped:   {skipped_count}")
    print(f"failed:    {failed_count}")
    print("=" * 80)


if __name__ == "__main__":
    main()