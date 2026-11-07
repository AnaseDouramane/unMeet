from scripts.export_eval_sample import sample_records


def test_sample_is_stratified_by_source_and_reproducible() -> None:
    rows = [("hackernews", str(i), f"hn {i}") for i in range(50)] + [
        ("reddit", str(i), f"reddit {i}") for i in range(3)
    ]

    first = sample_records(rows, per_source=10, seed=1)
    second = sample_records(rows, per_source=10, seed=1)

    assert first == second
    assert sum(record["category"] == "hackernews" for record in first) == 10
    assert sum(record["category"] == "reddit" for record in first) == 3
    assert len({record["id"] for record in first}) == 13
