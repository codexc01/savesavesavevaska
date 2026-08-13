"""Main entrypoint for hosting platforms (BotHost.ru / Render / VPS)."""

import asyncio
from app.bot import main

if __name__ == "__main__":
    asyncio.run(main())
