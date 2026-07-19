def test_extract_text_from_file_strips_embedded_nul_bytes():
    from app.services.knowledge_service import extract_text_from_file

    content = "hello\x00world\x00".encode("utf-8")
    text = extract_text_from_file(content, "notes.txt", "text/plain")

    assert "\x00" not in text
    assert text == "helloworld"


def test_extract_text_from_file_routes_images_through_gemini():
    from unittest.mock import patch
    from app.services import knowledge_service

    with patch.object(knowledge_service, "gemini_extract_document_text", return_value="OCR'd text") as mock_extract:
        text = knowledge_service.extract_text_from_file(
            b"fake-image-bytes", "photo.jpg", "image/jpeg", tenant_id="tenant-1"
        )

    assert text == "OCR'd text"
    mock_extract.assert_called_once_with(b"fake-image-bytes", "image/jpeg", tenant_id="tenant-1")


def test_extract_text_from_file_image_failure_propagates_as_value_error_message():
    from unittest.mock import patch
    from app.services import knowledge_service

    with patch.object(
        knowledge_service, "gemini_extract_document_text",
        side_effect=RuntimeError("gemini_api_key not configured for this client"),
    ):
        import pytest
        with pytest.raises(ValueError, match="Could not extract text from photo.jpg"):
            knowledge_service.extract_text_from_file(
                b"fake-image-bytes", "photo.jpg", "image/jpeg", tenant_id="tenant-1"
            )


def test_extract_text_from_file_pdf_with_real_text_layer_never_calls_gemini():
    from unittest.mock import patch, MagicMock
    from app.services import knowledge_service

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Real extracted PDF text"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch.object(knowledge_service.pdfplumber, "open", return_value=mock_pdf), \
         patch.object(knowledge_service, "gemini_extract_document_text") as mock_gemini_pdf:
        text = knowledge_service.extract_text_from_file(
            b"fake-pdf-bytes", "notes.pdf", "application/pdf", tenant_id="tenant-1"
        )

    assert text == "Real extracted PDF text"
    mock_gemini_pdf.assert_not_called()


def test_extract_text_from_file_scanned_pdf_falls_back_to_gemini():
    from unittest.mock import patch, MagicMock
    from app.services import knowledge_service

    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch.object(knowledge_service.pdfplumber, "open", return_value=mock_pdf), \
         patch.object(knowledge_service, "gemini_extract_document_text", return_value="OCR'd scanned text") as mock_gemini_pdf:
        text = knowledge_service.extract_text_from_file(
            b"fake-scanned-pdf-bytes", "scan.pdf", "application/pdf", tenant_id="tenant-1"
        )

    assert text == "OCR'd scanned text"
    mock_gemini_pdf.assert_called_once_with(b"fake-scanned-pdf-bytes", "application/pdf", tenant_id="tenant-1")
