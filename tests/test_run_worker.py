from types import SimpleNamespace

from app.ingestion.cursors import InMemoryCursorStore
from app.ingestion.runs import InMemoryRunStore
from scripts import run_worker


class Source:
    source = "reddit"

    def fetch(self):
        return iter(())


def _settings():
    return SimpleNamespace(
        poll_interval_seconds=60, poll_max_backoff_seconds=600, poll_stall_after_seconds=900
    )


def test_setup_errors_exit_before_looping(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_worker, "Settings", _settings)

    def broken(settings):
        raise ValueError("LLM_MODEL must be set")

    monkeypatch.setattr(run_worker, "build_ingestion", broken)

    assert run_worker.main() == 1
    assert "LLM_MODEL must be set" in capsys.readouterr().err


def test_clean_stop_returns_zero_and_wires_the_cursor_store(monkeypatch) -> None:
    seen = {}

    class FakeWorker:
        def __init__(self, pipeline, connectors, cursor_store, **kwargs):
            seen.update(connectors=connectors, store=cursor_store, kwargs=kwargs)
            self.health = {"reddit": object()}

        def run(self, stop):
            return 4

    monkeypatch.setattr(run_worker, "Settings", _settings)
    monkeypatch.setattr(
        run_worker,
        "build_ingestion",
        lambda settings: SimpleNamespace(pipeline=object(), connectors=(Source(),)),
    )
    monkeypatch.setattr(run_worker, "PollingWorker", FakeWorker)
    monkeypatch.setattr(run_worker, "SourceCursorRepository", InMemoryCursorStore)
    monkeypatch.setattr(run_worker, "IngestionRunRepository", InMemoryRunStore)
    monkeypatch.setattr(run_worker.signal, "signal", lambda *args: None)

    assert run_worker.main() == 0
    assert isinstance(seen["store"], InMemoryCursorStore)
    recorder = seen["kwargs"].pop("recorder")
    assert isinstance(recorder, InMemoryRunStore)
    assert seen["kwargs"] == {
        "interval_seconds": 60,
        "max_backoff_seconds": 600,
        "stall_after_seconds": 900,
    }
