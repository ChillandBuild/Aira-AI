def test_extract_text_from_file_strips_embedded_nul_bytes():
    from app.services.knowledge_service import extract_text_from_file

    content = "hello\x00world\x00".encode("utf-8")
    text = extract_text_from_file(content, "notes.txt", "text/plain")

    assert "\x00" not in text
    assert text == "helloworld"
