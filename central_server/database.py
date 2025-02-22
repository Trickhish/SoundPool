from urllib.parse import quote_plus
from sqlalchemy import DateTime, create_engine, Column, Integer, String, Boolean, ForeignKey, select
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from configuration import config,ConfigError
from db_models import *


if (not config):
    raise Exception("Failed to load the config")

if (config["database"]["engine"]=="sqlite"):
    db_url= f"sqlite:///./{config['database']['name']}"
elif config['database']['engine'] in ["mysql", "mariadb"]:
    try:
        import pymysql
    except ImportError:
        raise ConfigError(f"'pymysql' needs to be installed to use '{config['database']['engine']}' databases.")

    cdpass = quote_plus(config['database']['password'])
    port = config['database'].get('port', 3306)
    db_url = f"mysql+pymysql://{config['database']['user']}:{cdpass}@{config['database']['host']}:{port}/{config['database']['name']}"
elif config['database']["engine"]=='postgresql':
    try:
        import psycopg2
    except ImportError:
        raise ConfigError(f"'psycopg2' needs to be installed to use '{config['database']['engine']}' databases.")
    
    cdpass = quote_plus(config['database']['password'])
    port = config['database'].get('port', 5432)
    db_url = f"postgresql+psycopg2://{config['database']['user']}:{cdpass}@{config['database']['host']}:{port}/{config['database']['name']}"
else:
    raise ConfigError(f"'{config['database']['engine']}' databases aren't supported")

engine = create_engine(db_url, connect_args=({"check_same_thread": False} if (config["database"]["engine"]=="sqlite") else {}))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()