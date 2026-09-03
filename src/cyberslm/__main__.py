from __future__ import annotations

import uvicorn

from cyberslm.config import settings


def main() -> None:
    uvicorn.run(
        "cyberslm.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
