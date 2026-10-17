from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

async_engine = create_async_engine(
    'sqlite:///db.sqlite',
    echo=False,
)

async_session_factory = async_sessionmaker(async_engine)