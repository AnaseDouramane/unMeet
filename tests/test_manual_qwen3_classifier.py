import pytest

from scripts import test_qwen3_classifier


class FailingDeviceClassifier:
    def __init__(self, error: Exception) -> None:
        self.error = error

    @property
    def device_name(self) -> str:
        raise self.error


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ImportError("No module named 'torch'"), "Unable to import a required dependency"),
        (RuntimeError("CUDA was requested but is not available"), "Unable to select a device"),
    ],
)
def test_manual_entry_point_handles_dependency_and_device_errors(
    monkeypatch, capsys, error, message
) -> None:
    classifier = FailingDeviceClassifier(error)
    monkeypatch.setattr(test_qwen3_classifier, "Qwen3ProblemClassifier", lambda: classifier)

    assert test_qwen3_classifier.main() == 1

    output = capsys.readouterr().out
    assert message in output
    assert str(error) in output
