# app/models.py

import datetime
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    UniqueConstraint,
    Index
)
from sqlalchemy.orm import relationship, declarative_base

# SQLAlchemyの基本的な設定
Base = declarative_base()

# --- 1. 市場データテーブル (既存の設計を完全維持) ---

class TechnicalIndicator(Base):
    """
    テクニカル指標テーブル
    """
    __tablename__ = 'technical_indicators'
    __table_args__ = (
        UniqueConstraint('currency_pair', 'timestamp', name='uq_pair_time'),
    )

    id = Column(Integer, primary_key=True)
    currency_pair = Column(String) # 既存の 'currency_pair' を使用
    timestamp = Column(DateTime)
    close = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    sma_20 = Column(Float)
    ema_50 = Column(Float)
    bb_upper = Column(Float)
    bb_lower = Column(Float)
    adx = Column(Float)

class NewsArticle(Base):
    """
    ニュース記事テーブル
    """
    __tablename__ = 'news_articles'

    id = Column(Integer, primary_key=True)
    category = Column(String)
    title = Column(String)
    summary = Column(String)
    url = Column(String, unique=True) # unique制約を維持
    published = Column(DateTime)
    currency_tags = Column(JSON, default=[])

# --- 2. 【新規追加】推論・取引・評価の中核テーブル ---

class TradeInference(Base):
    """
    取引推論ログテーブル
    取引LLMの全ての思考プロセスを記録する、システムの中心となるテーブル。
    """
    __tablename__ = 'trade_inferences'

    id = Column(Integer, primary_key=True, comment="推論のユニークID")
    slack_message_ts = Column(String, unique=True, index=True, comment="Slackメッセージのタイムスタンプ(重複取得防止用の一意キー)")
    inference_time = Column(DateTime, nullable=False, index=True, default=datetime.datetime.utcnow, comment="推論実行日時")
    prompt = Column(Text, nullable=False, comment="LLMへの入力プロンプト全文")
    raw_response = Column(Text, nullable=False, comment="LLMからの生レスポンス全文")
    inferred_actions = Column(JSON, comment="構造化された推論アクション (例: [{'action': 'BUY', 'pair': 'USDJPY'}])")

    # この推論から生まれた「実績取引」へのリレーション (1対多)
    actual_trades = relationship("ActualTrade", back_populates="inference")
    # この推論に対する「評価」へのリレーション (1対1)
    evaluation = relationship("TradeEvaluation", back_populates="inference", uselist=False, cascade="all, delete-orphan")

class ActualTrade(Base):
    """
    実績取引ログテーブル
    実際に行われた取引の履歴を保存する。JSONからのインポートを想定。
    """
    __tablename__ = 'actual_trades'

    id = Column(Integer, primary_key=True, comment="取引のユニークID")
    # この取引の判断根拠となった推論ID。どの推論を見て取引したかを紐付ける。
    inference_id = Column(Integer, ForeignKey('trade_inferences.id'), nullable=True, index=True, comment="関連する推論ID (手動取引の場合はNULL)")
    trade_time = Column(DateTime, nullable=False, index=True, comment="取引実行日時")
    pair = Column(String(10), nullable=False, comment="通貨ペア")
    action = Column(String(10), nullable=False, comment="売買アクション ('BUY' or 'SELL')")
    entry_price = Column(Float, nullable=False, comment="エントリー価格")
    exit_price = Column(Float, comment="決済価格")
    amount = Column(Float, nullable=False, comment="取引数量")
    profit_loss = Column(Float, comment="確定損益 (金額)")

    # どの「推論」に基づいた取引かを示すリレーション
    inference = relationship("TradeInference", back_populates="actual_trades")

class TradeEvaluation(Base):
    """
    取引評価テーブル
    評価エンジンによる各推論のレビュー結果を保存する。システムの「知性」が蓄積される場所。
    """
    __tablename__ = 'trade_evaluations'

    id = Column(Integer, primary_key=True, comment="評価のユニークID")
    # 評価対象の推論ID。一つの推論に一つの評価。
    inference_id = Column(Integer, ForeignKey('trade_inferences.id'), nullable=False, unique=True, index=True, comment="評価対象の推論ID")
    evaluation_time = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, comment="評価実行日時")
    
    # --- 評価内容 ---
    logic_evaluation_score = Column(Integer, comment="ロジック妥当性スコア (1-5点)")
    logic_evaluation_comment = Column(Text, comment="ロジック妥当性に関する評価コメント")
    potential_profit_loss = Column(Float, comment="ポテンシャル評価（仮想取引）での損益")
    evaluation_summary = Column(Text, comment="この推論と結果から得られる総括")

    # 評価対象の「推論」へのリレーション
    inference = relationship("TradeInference", back_populates="evaluation")
