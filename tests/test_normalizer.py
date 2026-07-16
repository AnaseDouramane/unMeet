from app.preprocessing.normalizer import build_document_text


def test_build_document_text_joins_title_and_body() -> None:
    assert build_document_text("Hello", "World") == "Hello\n\nWorld"


def test_build_document_text_skips_empty_parts() -> None:
    assert build_document_text("  Hello  ", "   ") == "Hello"
