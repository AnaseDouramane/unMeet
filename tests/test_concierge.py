from datetime import UTC, datetime

import pytest

from app.concierge.service import (
    FEEDBACK_COLUMNS,
    feedback_sheet,
    parse_feedback,
    render_digest,
    states_from_feedback,
    summarize,
    wilson_interval,
)
from app.inbox.schemas import InboxItem
from scripts import concierge

DAY = datetime(2026, 11, 9, tzinfo=UTC)


def item(i, quote="I spend hours deduping", **kw):
    values = dict(
        signal_id=i,
        source="reddit",
        title=f"Post {i}",
        url=f"https://x.test/{i}",
        author="secret_user",
        published_at=DAY,
        intent="pain_point",
        pain_quote=quote,
        products_mentioned=(),
        severity=2,
        topic_id=1,
        topic_name="CRM",
        relevance_reason="asks for a dedupe tool",
    )
    values.update(kw)
    return InboxItem(**values)


def test_the_digest_is_email_ready_quotes_verbatim_and_never_names_authors() -> None:
    text = render_digest(
        (item(1), item(2, quote=None)), "Acme", DAY, {1: "Disclosure: I work at Acme. Try merging."}
    )

    assert text.startswith("# 2 conversation(s) for Acme — 2026-11-09")
    assert (
        "> I spend hours deduping" in text and "**Why it matches:** asks for a dedupe tool" in text
    )
    assert "[Open the conversation](https://x.test/1)" in text
    assert "> Disclosure: I work at Acme. Try merging." in text and text.count("Reply draft") == 1
    assert "secret_user" not in text and "Nothing was posted on your behalf" in text


def test_the_sheet_has_empty_answer_columns_and_neutralises_formulas() -> None:
    import csv
    import io

    rows = list(
        csv.DictReader(io.StringIO(feedback_sheet((item(1), item(2, quote='=HYPERLINK("x")')))))
    )
    assert tuple(rows[0]) == FEEDBACK_COLUMNS
    assert rows[0]["useful"] == "" and rows[0]["would_reply"] == "" and rows[0]["signal_id"] == "1"
    assert rows[1]["quote"].startswith("'=")


def test_answers_are_read_leniently_and_summarised_with_an_interval() -> None:
    sheet = (
        "signal_id,useful,would_reply,notes\n"
        "1,yes,yes,great\n2,Sì,no,\n3,no,,noise\n4,,,\n5,maybe,,\nabc,yes,yes,\n6,Y,y,\n"
    )
    rows = parse_feedback(sheet)
    assert [r.signal_id for r in rows] == [1, 2, 3, 4, 5, 6]  # the bad id row is skipped
    assert [r.useful for r in rows] == [True, True, False, None, None, True]

    summary = summarize(rows)
    assert (summary.answered, summary.useful, summary.would_reply, summary.unanswered) == (
        4,
        3,
        2,
        2,
    )
    assert summary.precision == 0.75 and summary.low < 0.75 < summary.high


def test_states_follow_the_answers() -> None:
    rows = parse_feedback("signal_id,useful,would_reply\n1,yes,yes\n2,yes,no\n3,no,\n4,,\n")
    assert states_from_feedback(rows) == {"replied": [1], "relevant": [2], "not_relevant": [3]}


def test_no_answers_means_no_number() -> None:
    summary = summarize(parse_feedback("signal_id,useful,would_reply\n1,,\n"))
    assert summary.precision is None and summary.unanswered == 1


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(8, 10, 0.49, 0.94), (80, 100, 0.71, 0.87), (0, 5, 0.0, 0.43), (5, 5, 0.57, 1.0)],
)
def test_wilson_interval_matches_known_values(k, n, low, high) -> None:
    got_low, got_high = wilson_interval(k, n)
    assert got_low == pytest.approx(low, abs=0.02) and got_high == pytest.approx(high, abs=0.02)
    with pytest.raises(ValueError):
        wilson_interval(0, 0)


def test_ten_answers_are_a_wide_band() -> None:
    low, high = wilson_interval(8, 10)
    assert high - low > 0.4  # 80% useful out of 10 says little: the tool must not hide that


def test_cli_writes_both_files_and_reads_the_answers_back(tmp_path, monkeypatch, capsys) -> None:
    states: dict[str, list[int]] = {}

    class Inbox:
        def list_items(self, workspace_id, topic_id=None, state="new", limit=50, offset=0):
            return (item(1), item(2))[:limit]

        def set_state(self, workspace_id, ids, state, *a, **k):
            states[state] = list(ids)
            return len(ids)

    class Tenancy:
        def get_workspace(self, workspace_id):
            from app.tenancy.schemas import Workspace

            return Workspace(workspace_id, "Acme", "acme", "free")

    monkeypatch.setattr(concierge, "InboxRepository", Inbox)
    monkeypatch.setattr(concierge, "TenancyRepository", Tenancy)

    assert (
        concierge.main(["digest", "--workspace", "1", "--count", "2", "--out", str(tmp_path)]) == 0
    )
    digest, sheet = sorted(tmp_path.iterdir())
    assert digest.name.startswith("digest-") and sheet.name.startswith("feedback-")

    filled = sheet.read_text().replace("1,CRM,reddit", "1,CRM,reddit")
    lines = filled.splitlines()
    lines[1] = lines[1].rsplit(",,,", 1)[0] + ",yes,yes,"
    lines[2] = lines[2].rsplit(",,,", 1)[0] + ",no,,"
    sheet.write_text("\n".join(lines) + "\n")
    capsys.readouterr()

    assert concierge.main(["results", str(sheet), "--workspace", "1"]) == 0
    out = capsys.readouterr().out
    assert "Useful: 1/2 = 50%" in out and "Small sample" in out
    assert states == {"replied": [1], "not_relevant": [2]}


def test_cli_reports_an_empty_inbox_and_a_missing_workspace(tmp_path, monkeypatch, capsys) -> None:
    class Empty:
        def list_items(self, *a, **k):
            return ()

    class Missing:
        def get_workspace(self, workspace_id):
            return None

    monkeypatch.setattr(concierge, "InboxRepository", Empty)
    monkeypatch.setattr(concierge, "TenancyRepository", Missing)
    assert concierge.main(["digest", "--workspace", "9", "--out", str(tmp_path)]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_cli_says_when_there_is_nothing_new_and_writes_no_files(
    tmp_path, monkeypatch, capsys
) -> None:
    class Empty:
        def list_items(self, *a, **k):
            return ()

    class Tenancy:
        def get_workspace(self, workspace_id):
            from app.tenancy.schemas import Workspace

            return Workspace(workspace_id, "Acme", "acme", "free")

    monkeypatch.setattr(concierge, "InboxRepository", Empty)
    monkeypatch.setattr(concierge, "TenancyRepository", Tenancy)
    assert concierge.main(["digest", "--workspace", "1", "--out", str(tmp_path)]) == 0
    assert "nothing new" in capsys.readouterr().out and list(tmp_path.iterdir()) == []
