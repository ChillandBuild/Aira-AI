def test_extract_text_from_file_strips_embedded_nul_bytes():
    from app.services.knowledge_service import extract_text_from_file

    content = "hello\x00world\x00".encode("utf-8")
    text = extract_text_from_file(content, "notes.txt", "text/plain")

    assert "\x00" not in text
    assert text == "helloworld"


def test_extract_text_from_file_routes_images_through_sarvam():
    from unittest.mock import patch
    from app.services import knowledge_service

    with patch.object(knowledge_service, "get_sarvam_api_key", return_value="test-key") as mock_get_key, \
         patch.object(knowledge_service, "extract_text_from_image", return_value="OCR'd text") as mock_extract:
        text = knowledge_service.extract_text_from_file(
            b"fake-image-bytes", "photo.jpg", "image/jpeg", tenant_id="tenant-1"
        )

    assert text == "OCR'd text"
    mock_get_key.assert_called_once_with("tenant-1")
    mock_extract.assert_called_once_with(b"fake-image-bytes", "image/jpeg", "test-key")


def test_extract_text_from_file_image_failure_propagates_as_value_error_message():
    from unittest.mock import patch
    from app.services import knowledge_service

    with patch.object(knowledge_service, "get_sarvam_api_key", return_value="test-key"), \
         patch.object(
             knowledge_service, "extract_text_from_image",
             side_effect=RuntimeError("Sarvam Document Digitization job job-1 ended in state 'Failed'"),
         ):
        import pytest
        with pytest.raises(ValueError, match="Could not extract text from photo.jpg"):
            knowledge_service.extract_text_from_file(
                b"fake-image-bytes", "photo.jpg", "image/jpeg", tenant_id="tenant-1"
            )
