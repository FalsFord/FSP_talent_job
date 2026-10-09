"""CLI загрузки корпуса:  python -m app.tasks.rag.ingest --path /data/ru-test-assignments [--builtin-only]

Корпус Hexlet/ru-test-assignments НЕ входит в репозиторий проекта (лицензия AGPL-3.0, тексты принадлежат компаниям):
клонируйте его отдельно (git clone https://github.com/Hexlet/ru-test-assignments) и укажите путь."""
import argparse
import asyncio
from pathlib import Path

from app.db.session import SessionLocal, engine
from app.services import knowledge_service as ks


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None, help="каталог с клоном ru-test-assignments")
    ap.add_argument("--builtin-only", action="store_true")
    args = ap.parse_args()
    async with SessionLocal() as db:
        print("builtin:", await ks.ingest_builtin(db))
        if not args.builtin_only:
            from app.core.config import settings

            root = Path(args.path or settings.knowledge_dir)
            if root.is_dir():
                print("corpus:", await ks.ingest_directory(db, root))
            else:
                print(f"каталог корпуса не найден: {root} (пропущено; работает встроенный корпус)")
        print("stats:", await ks.knowledge_stats(db))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
