from app.database.base import Base
from app.database.session import engine
import app.database.models  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")


if __name__ == "__main__":
    main()
