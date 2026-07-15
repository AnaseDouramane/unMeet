from app.preprocessing.deduplicator import text_hash


def test_text_hash_is_case_and_space_insensitive() -> None:
    assert text_hash("Hello  World") == text_hash("hello world")
