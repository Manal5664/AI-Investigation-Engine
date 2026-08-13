"""Production-oriented launcher.

Reads HOST and PORT from the application settings (both can come from the
environment; ``PORT`` is commonly injected by deployment platforms) and serves
the application with a single uvicorn worker.

Local development keeps using the reload server instead:

    python -m uvicorn app.main:app --reload
"""

import uvicorn

from app.core.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
    )


if __name__ == "__main__":
    main()
