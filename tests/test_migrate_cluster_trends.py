from scripts import migrate_cluster_trends


def test_migration_creates_the_trend_table_idempotently(monkeypatch, capsys) -> None:
    calls = []

    def create(*, bind, checkfirst: bool) -> None:
        calls.append((bind, checkfirst))

    monkeypatch.setattr(migrate_cluster_trends.ClusterTrendModel.__table__, "create", create)

    assert migrate_cluster_trends.main() == 0

    assert calls == [(migrate_cluster_trends.engine, True)]
    assert "schema is up to date" in capsys.readouterr().out
