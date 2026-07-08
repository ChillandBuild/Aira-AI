import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.sarvam_document_intelligence import (
    _extract_markdown_from_output_zip,
    _zip_single_image,
    extract_text_from_image,
    extract_text_from_pdf,
)


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestZipSingleImage:
    def test_zip_single_image_jpeg(self):
        zip_bytes, zip_filename = _zip_single_image(b"fake-jpeg-bytes", "image/jpeg")
        assert zip_filename == "image.zip"
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.namelist() == ["image.jpg"]
            assert zf.read("image.jpg") == b"fake-jpeg-bytes"

    def test_zip_single_image_png(self):
        zip_bytes, _ = _zip_single_image(b"fake-png-bytes", "image/png")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.namelist() == ["image.png"]

    def test_zip_single_image_rejects_unsupported_mime(self):
        with pytest.raises(ValueError, match="JPEG/PNG"):
            _zip_single_image(b"fake-webp-bytes", "image/webp")


class TestExtractMarkdownFromOutputZip:
    def test_extracts_and_joins_markdown_files_only(self):
        zip_bytes = _make_zip({
            "page_1.md": "# Page 1",
            "page_2.md": "# Page 2",
            "metadata.json": '{"pages": 2}',
        })
        text = _extract_markdown_from_output_zip(zip_bytes)
        assert text == "# Page 1\n\n# Page 2"

    def test_empty_zip_returns_empty_string(self):
        zip_bytes = _make_zip({"metadata.json": "{}"})
        assert _extract_markdown_from_output_zip(zip_bytes) == ""


class TestExtractTextFromImage:
    def _mock_response(self, json_data=None, content=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if json_data is not None:
            resp.json.return_value = json_data
        if content is not None:
            resp.content = content
        return resp

    def test_success_immediate_completion(self):
        output_zip = _make_zip({"page_1.md": "Extracted text here"})
        create_resp = self._mock_response({"job_id": "job-123"})
        upload_resp = self._mock_response({
            "upload_urls": {"image.zip": {"file_url": "https://upload.example/presigned"}}
        })
        put_resp = self._mock_response()
        start_resp = self._mock_response({"job_state": "Completed"})
        download_resp = self._mock_response({
            "download_urls": {"output.zip": {"file_url": "https://download.example/output.zip"}}
        })
        zip_get_resp = self._mock_response(content=output_zip)

        mock_client = MagicMock()
        mock_client.post.side_effect = [create_resp, upload_resp, start_resp, download_resp]
        mock_client.put.return_value = put_resp
        mock_client.get.return_value = zip_get_resp

        with patch("app.services.sarvam_document_intelligence.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_client
            text = extract_text_from_image(b"fake-jpeg-bytes", "image/jpeg", "test-key")

        assert text == "Extracted text here"

        create_call = mock_client.post.call_args_list[0]
        assert create_call.args[0] == "https://api.sarvam.ai/doc-digitization/job/v1"
        assert create_call.kwargs["headers"] == {"api-subscription-key": "test-key"}
        assert create_call.kwargs["json"] == {"language": "unknown", "output_format": "md"}

        upload_call = mock_client.post.call_args_list[1]
        assert upload_call.args[0] == "https://api.sarvam.ai/doc-digitization/job/v1/upload-files"
        assert upload_call.kwargs["json"] == {"job_id": "job-123", "files": ["image.zip"]}

        put_call = mock_client.put.call_args
        assert put_call.args[0] == "https://upload.example/presigned"

        start_call = mock_client.post.call_args_list[2]
        assert start_call.args[0] == "https://api.sarvam.ai/doc-digitization/job/v1/job-123/start"

        download_call = mock_client.post.call_args_list[3]
        assert download_call.args[0] == "https://api.sarvam.ai/doc-digitization/job/v1/job-123/download-files"

    def test_polls_until_completed(self):
        output_zip = _make_zip({"page_1.md": "Polled result"})
        create_resp = self._mock_response({"job_id": "job-456"})
        upload_resp = self._mock_response({
            "upload_urls": {"image.zip": {"file_url": "https://upload.example/presigned"}}
        })
        start_resp = self._mock_response({"job_state": "Pending"})
        download_resp = self._mock_response({
            "download_urls": {"output.zip": {"file_url": "https://download.example/output.zip"}}
        })
        status_running = self._mock_response({"job_state": "Running"})
        status_completed = self._mock_response({"job_state": "Completed"})
        zip_get_resp = self._mock_response(content=output_zip)

        mock_client = MagicMock()
        mock_client.post.side_effect = [create_resp, upload_resp, start_resp, download_resp]
        mock_client.put.return_value = self._mock_response()
        mock_client.get.side_effect = [status_running, status_completed, zip_get_resp]

        with patch("app.services.sarvam_document_intelligence.httpx.Client") as mock_client_cls, \
             patch("app.services.sarvam_document_intelligence.time.sleep"), \
             patch("app.services.sarvam_document_intelligence.time.monotonic", return_value=0):
            mock_client_cls.return_value.__enter__.return_value = mock_client
            text = extract_text_from_image(b"fake-png-bytes", "image/png", "test-key")

        assert text == "Polled result"
        assert mock_client.get.call_count == 3
        status_urls = [c.args[0] for c in mock_client.get.call_args_list[:2]]
        assert all(u == "https://api.sarvam.ai/doc-digitization/job/v1/job-456/status" for u in status_urls)

    def test_raises_on_failed_job_state(self):
        create_resp = self._mock_response({"job_id": "job-789"})
        upload_resp = self._mock_response({
            "upload_urls": {"image.zip": {"file_url": "https://upload.example/presigned"}}
        })
        start_resp = self._mock_response({"job_state": "Failed"})

        mock_client = MagicMock()
        mock_client.post.side_effect = [create_resp, upload_resp, start_resp]
        mock_client.put.return_value = self._mock_response()

        with patch("app.services.sarvam_document_intelligence.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_client
            with pytest.raises(RuntimeError, match="Failed"):
                extract_text_from_image(b"fake-jpeg-bytes", "image/jpeg", "test-key")

    def test_raises_timeout_error_when_job_never_completes(self):
        create_resp = self._mock_response({"job_id": "job-timeout"})
        upload_resp = self._mock_response({
            "upload_urls": {"image.zip": {"file_url": "https://upload.example/presigned"}}
        })
        start_resp = self._mock_response({"job_state": "Running"})

        mock_client = MagicMock()
        mock_client.post.side_effect = [create_resp, upload_resp, start_resp]
        mock_client.put.return_value = self._mock_response()

        with patch("app.services.sarvam_document_intelligence.httpx.Client") as mock_client_cls, \
             patch("app.services.sarvam_document_intelligence.time.sleep"), \
             patch("app.services.sarvam_document_intelligence.time.monotonic", side_effect=[0, 1000]):
            mock_client_cls.return_value.__enter__.return_value = mock_client
            with pytest.raises(TimeoutError, match="timed out"):
                extract_text_from_image(b"fake-jpeg-bytes", "image/jpeg", "test-key")

    def test_rejects_unsupported_mime_before_any_api_call(self):
        with pytest.raises(ValueError, match="JPEG/PNG"):
            extract_text_from_image(b"fake-webp-bytes", "image/webp", "test-key")


class TestExtractTextFromPdf:
    def _mock_response(self, json_data=None, content=None):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if json_data is not None:
            resp.json.return_value = json_data
        if content is not None:
            resp.content = content
        return resp

    def test_uploads_raw_pdf_bytes_without_zip_wrapping(self):
        output_zip = _make_zip({"page_1.md": "Scanned PDF text"})
        create_resp = self._mock_response({"job_id": "job-pdf-1"})
        upload_resp = self._mock_response({
            "upload_urls": {"document.pdf": {"file_url": "https://upload.example/presigned"}}
        })
        put_resp = self._mock_response()
        start_resp = self._mock_response({"job_state": "Completed"})
        download_resp = self._mock_response({
            "download_urls": {"output.zip": {"file_url": "https://download.example/output.zip"}}
        })
        zip_get_resp = self._mock_response(content=output_zip)

        mock_client = MagicMock()
        mock_client.post.side_effect = [create_resp, upload_resp, start_resp, download_resp]
        mock_client.put.return_value = put_resp
        mock_client.get.return_value = zip_get_resp

        with patch("app.services.sarvam_document_intelligence.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = mock_client
            text = extract_text_from_pdf(b"fake-pdf-bytes", "test-key")

        assert text == "Scanned PDF text"

        create_call = mock_client.post.call_args_list[0]
        assert create_call.kwargs["json"] == {"language": "unknown", "output_format": "md"}

        upload_call = mock_client.post.call_args_list[1]
        assert upload_call.kwargs["json"] == {"job_id": "job-pdf-1", "files": ["document.pdf"]}

        put_call = mock_client.put.call_args
        assert put_call.args[0] == "https://upload.example/presigned"
        assert put_call.kwargs["content"] == b"fake-pdf-bytes"
