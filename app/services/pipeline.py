from app.config import Settings


class Pipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self) -> None:
        print("unMeet pipeline initialized.")
        print(f"Environment: {self.settings.environment}")
        print("Next step: implement ingestion connectors.")
