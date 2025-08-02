# app/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# 環境変数からDB URLを取得、デフォルトはSQLite
DATABASE_URL = os.getenv("DB_PATH", "sqlite:///./db/forex.sqlite")

# SQLAlchemyエンジンの作成
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# セッションファクトリの作成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """
    データベーステーブルを作成する
    アプリケーション起動時に呼び出される
    """
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    データベースセッションを取得するジェネレータ
    FastAPIの依存性注入で使用される
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
