from app.preprocessing.cleaner import clean_text


def test_clean_text_removes_html_and_extra_spaces() -> None:
    assert clean_text("<p>Hello   world</p>") == "Hello world"
