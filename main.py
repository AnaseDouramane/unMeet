from app.config import settings
from app.services.pipeline import Pipeline


def main() -> None:
    pipeline = Pipeline(settings=settings)
    pipeline.run()


if __name__ == "__main__":
    main()
