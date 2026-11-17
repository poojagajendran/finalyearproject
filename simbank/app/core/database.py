from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from simbank.app.core.config import simbank_settings

connect_args = {}
if simbank_settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

bank_engine = create_async_engine(
    simbank_settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True
)

BankAsyncSessionLocal = async_sessionmaker(
    bind=bank_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

class BankBase(DeclarativeBase):
    pass

async def get_bank_db() -> AsyncSession:
    async with BankAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
