# backend/app/services/sarvam_document_intelligence.py
"""Sarvam Document Digitization: create -> upload -> start -> poll -> download -> unzip.
Synchronous by design -- the only caller (knowledge_service.extract_text_from_file) is
itself a sync function run inside asyncio.to_thread, so a blocking httpx.Client + time.sleep
poll loop matches the existing execution model without needing an async rewrite."""
import io
import time
import zipfile

import httpx

from app.services.sarvam_client import SARVAM_BASE_URL

_DOC_DIGITIZATION_BASE = f"{SARVAM_BASE_URL}/doc-digitization/job/v1"
_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 120.0
_IN_PROGRESS_STATES = {"Accepted", "Pending", "Running"}
_SUCCESS_STATES = {"Completed", "PartiallyCompleted"}

# Sarvam's Document Digitization only accepts PDF or ZIP uploads, and a ZIP's images
# must be JPEG/PNG -- unlike Groq's vision model, which took any image/* mime type
# directly as a data URL. Other formats (webp/gif/bmp) are rejected before any API call.
_IMAGE_EXT_BY_MIME = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png"}


def _zip_single_image(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    ext = _IMAGE_EXT_BY_MIME.get(mime_type.lower())
    if not ext:
        raise ValueError(
            f"Sarvam Document Digitization only accepts JPEG/PNG images, got {mime_type}"
        )
    zip_filename = "image.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"image.{ext}", image_bytes)
    return buf.getvalue(), zip_filename


def _extract_markdown_from_output_zip(zip_bytes: bytes) -> str:
    parts = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in sorted(zf.namelist()):
            if name.lower().endswith(".md"):
                parts.append(zf.read(name).decode("utf-8"))
    return "\n\n".join(parts).strip()


def _run_digitization_job(file_bytes: bytes, filename: str, api_key: str, language: str) -> str:
    """Shared create -> upload -> start -> poll -> download -> unzip lifecycle. Raises on
    any step failure -- knowledge_service.py's caller already wraps extract_text_from_file
    in a try/except that marks the document 'failed' with str(e), so errors here surface
    to the user rather than being swallowed."""
    headers = {"api-subscription-key": api_key}

    with httpx.Client(timeout=60.0) as client:
        create_resp = client.post(
            _DOC_DIGITIZATION_BASE,
            headers=headers,
            json={"language": language, "output_format": "md"},
        )
        create_resp.raise_for_status()
        job_id = create_resp.json()["job_id"]

        upload_resp = client.post(
            f"{_DOC_DIGITIZATION_BASE}/upload-files",
            headers=headers,
            json={"job_id": job_id, "files": [filename]},
        )
        upload_resp.raise_for_status()
        file_url = upload_resp.json()["upload_urls"][filename]["file_url"]

        put_resp = client.put(file_url, content=file_bytes)
        put_resp.raise_for_status()

        start_resp = client.post(f"{_DOC_DIGITIZATION_BASE}/{job_id}/start", headers=headers)
        start_resp.raise_for_status()
        job_state = start_resp.json().get("job_state")

        deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
        while job_state in _IN_PROGRESS_STATES:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Sarvam Document Digitization job {job_id} timed out")
            time.sleep(_POLL_INTERVAL_SECONDS)
            status_resp = client.get(f"{_DOC_DIGITIZATION_BASE}/{job_id}/status", headers=headers)
            status_resp.raise_for_status()
            job_state = status_resp.json().get("job_state")

        if job_state not in _SUCCESS_STATES:
            raise RuntimeError(f"Sarvam Document Digitization job {job_id} ended in state {job_state!r}")

        download_resp = client.post(f"{_DOC_DIGITIZATION_BASE}/{job_id}/download-files", headers=headers)
        download_resp.raise_for_status()
        download_urls = download_resp.json()["download_urls"]
        output_file_url = next(iter(download_urls.values()))["file_url"]

        zip_resp = client.get(output_file_url)
        zip_resp.raise_for_status()

    return _extract_markdown_from_output_zip(zip_resp.content)


def extract_text_from_image(
    image_bytes: bytes, mime_type: str, api_key: str, language: str = "unknown"
) -> str:
    """Runs a full Sarvam Document Digitization job for a single image and returns the
    extracted markdown text. language="unknown" triggers Sarvam's own auto-detection
    across its 23 supported languages (22 Indian languages + English) -- previously
    hardcoded to "en-IN", which silently degraded extraction accuracy on any non-English
    upload."""
    zip_bytes, zip_filename = _zip_single_image(image_bytes, mime_type)
    return _run_digitization_job(zip_bytes, zip_filename, api_key, language)


def extract_text_from_pdf(pdf_bytes: bytes, api_key: str, language: str = "unknown") -> str:
    """Runs a full Sarvam Document Digitization job for a PDF and returns the extracted
    markdown text. Unlike images, Sarvam accepts PDF directly -- no ZIP wrapping needed.
    Intended as a fallback for scanned PDFs where pdfplumber's text-layer extraction comes
    back empty (pdfplumber has no OCR capability at all)."""
    return _run_digitization_job(pdf_bytes, "document.pdf", api_key, language)
