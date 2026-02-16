# LEGO: Convert PDF URLs → Metadata JSON Pipeline

This is lightweight local pipeline that automates the conversion of PDF URLs into structured metadata JSON objects using Google's Vertex AI + Gemini LLM. 

Given a webpage downloadable PDF URL , the pipeline will :
→ Download  
→ Text extraction using DocAI OCR
→ Metadata extraction using Gemini
→ Structured JSON raw document object
→ Saves outputs locally

The only initial input is "copy and paste the PDF URL".
The final output is a portable JSON file ready to be uploaded into a vector database.

# Requirements

- Python 3.10+
- Google Cloud Project
- Document AI processor
- Vertex AI access (Gemini enabled)

# Setup

## 1. Clone the repository
```bash
git clone <your-repo-url>
cd lego-pipeline
```

## 2. Create and activate venv
```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. Create the following local storage folders using the following names:
1. lego-raw-pdfs/                → downloaded PDFs
2. lego-extracted/               → Document AI outputs
3. lego-enriched/                → metadata.json + batch reports
4. lego-rawdoc-objects/
    ├── by-doc-id/            → canonical rawdoc JSON
    └── by-title/             → title alias JSON

## 4. Configure environment variables
Edit .env.local according to your own project variables. Use .env.example as template to copy and paste into .env.local.

# How To Use (Single URL)

## Step 1 — Activate venv
```bash
source .venv/bin/activate
```
## Step 2 — Copy PDF URL
Example:
https://www.ema.gov.sg/content/dam/...

## Step 3 — Run pipeline
```bash
python src/run_pipeline.py "<PDF_URL>"
## Example:
## python src/run_pipeline.py "https://www.ema.gov.sg/content/dam/..."
```

## Step 4 — Check output
- Final JSON file will be stored in: lego-rawdoc-objects/by-doc-id/
- Title alias file will also be stored in: lego-rawdoc-objects/by-title/


# Output Structure
```sql
lego-raw-pdfs/                → downloaded PDFs
lego-extracted/               → Document AI outputs
lego-enriched/                → metadata.json + batch reports
lego-rawdoc-objects/
    ├── by-doc-id/            → canonical rawdoc JSON
    └── by-title/             → title alias JSON
```

# Metadata Schema
Each final JSON object contains:
- doc_id
- source_url
- retrieved_at
- metadata:
    - title
    - agency
    - publication_date
    - type
    - status
    - topic
- content:
    - full_text
- provenance:
    - extraction method


# Notes
- Metadata extraction uses Gemini with strict JSON enforcement.
- JSON repair fallback is implemented.
- Large documents automatically use excerpt mode for stability.
- Duplicate PDFs are skipped automatically (based on doc_id hash).
