from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def run_startup_migrations() -> None:
    """Apply small idempotent migrations required by the FastAPI service."""
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            ALTER TABLE importacao_transacoes.customer
                ADD COLUMN IF NOT EXISTS score_csb8 numeric,
                ADD COLUMN IF NOT EXISTS score_csba numeric,
                ADD COLUMN IF NOT EXISTS score_csb8_faixa text,
                ADD COLUMN IF NOT EXISTS score_csba_faixa text,
                ADD COLUMN IF NOT EXISTS score_updated_at timestamptz;
            """
        )
        await connection.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS customer_score_missing_idx
                ON importacao_transacoes.customer (record_id)
                WHERE score_csb8 IS NULL AND score_csba IS NULL;
            """
        )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
