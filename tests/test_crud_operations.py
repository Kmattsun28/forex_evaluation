# tests/test_crud_operations.py

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, TradeInference, ActualTrade, TradeEvaluation
from app import crud, schemas

# テスト用のインメモリSQLiteデータベース
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def db_session():
    """テスト用データベースセッション"""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

def test_create_trade_inference(db_session):
    """推論作成のテスト"""
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="test_ts_123",
        inference_time=datetime.utcnow(),
        prompt="Test prompt for USDJPY",
        raw_response="I recommend BUY USDJPY based on technical analysis",
        inferred_actions=[{"action": "BUY", "pair": "USDJPY", "confidence": 0.8}]
    )
    
    created_inference = crud.create_trade_inference(db_session, inference_data)
    
    assert created_inference.id is not None
    assert created_inference.slack_message_ts == inference_data.slack_message_ts
    assert created_inference.prompt == inference_data.prompt
    assert len(created_inference.inferred_actions) == 1

def test_get_trade_inference(db_session):
    """推論取得のテスト"""
    # テストデータを作成
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="get_test_ts",
        inference_time=datetime.utcnow(),
        prompt="Get test prompt",
        raw_response="Get test response",
        inferred_actions=[]
    )
    created = crud.create_trade_inference(db_session, inference_data)
    
    # 取得テスト
    retrieved = crud.get_trade_inference(db_session, created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.slack_message_ts == inference_data.slack_message_ts

def test_get_trade_inference_by_slack_ts(db_session):
    """Slackタイムスタンプによる推論取得のテスト"""
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="slack_ts_test",
        inference_time=datetime.utcnow(),
        prompt="Slack TS test prompt",
        raw_response="Slack TS test response",
        inferred_actions=[]
    )
    created = crud.create_trade_inference(db_session, inference_data)
    
    # Slackタイムスタンプで取得
    retrieved = crud.get_trade_inference_by_slack_ts(db_session, "slack_ts_test")
    assert retrieved is not None
    assert retrieved.id == created.id

def test_create_actual_trade(db_session):
    """実績取引作成のテスト"""
    trade_data = schemas.ActualTradeCreate(
        trade_time=datetime.utcnow(),
        pair="USDJPY",
        action="BUY",
        entry_price=150.25,
        exit_price=150.75,
        amount=10000,
        profit_loss=500.0
    )
    
    created_trade = crud.create_actual_trade(db_session, trade_data)
    
    assert created_trade.id is not None
    assert created_trade.pair == trade_data.pair
    assert created_trade.action == trade_data.action
    assert created_trade.profit_loss == trade_data.profit_loss

def test_find_closest_inference_for_trade(db_session):
    """取引に最も近い推論の検索テスト"""
    # 基準時刻
    base_time = datetime.utcnow()
    
    # 複数の推論を作成（異なる時刻で）
    inference1_data = schemas.TradeInferenceCreate(
        slack_message_ts="closest_test_1",
        inference_time=base_time - timedelta(hours=1),  # 1時間前
        prompt="Test prompt 1",
        raw_response="Test response 1",
        inferred_actions=[]
    )
    inference1 = crud.create_trade_inference(db_session, inference1_data)
    
    inference2_data = schemas.TradeInferenceCreate(
        slack_message_ts="closest_test_2",
        inference_time=base_time + timedelta(minutes=30),  # 30分後
        prompt="Test prompt 2",
        raw_response="Test response 2",
        inferred_actions=[]
    )
    inference2 = crud.create_trade_inference(db_session, inference2_data)
    
    # 基準時刻での取引に最も近い推論を検索
    closest = crud.find_closest_inference_for_trade(db_session, base_time, time_window_hours=2)
    
    # 30分後の推論の方が近いはず
    assert closest is not None
    assert closest.id == inference2.id

def test_create_trade_evaluation(db_session):
    """評価作成のテスト"""
    # 先に推論を作成
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="eval_test_ts",
        inference_time=datetime.utcnow(),
        prompt="Evaluation test prompt",
        raw_response="Evaluation test response",
        inferred_actions=[]
    )
    inference = crud.create_trade_inference(db_session, inference_data)
    
    # 評価を作成
    evaluation_data = schemas.TradeEvaluationCreate(
        inference_id=inference.id,
        logic_evaluation_score=4,
        logic_evaluation_comment="Good analysis with clear reasoning",
        potential_profit_loss=250.0,
        evaluation_summary="Solid inference with good market analysis"
    )
    
    created_evaluation = crud.create_trade_evaluation(db_session, evaluation_data)
    
    assert created_evaluation.id is not None
    assert created_evaluation.inference_id == inference.id
    assert created_evaluation.logic_evaluation_score == 4
    assert created_evaluation.potential_profit_loss == 250.0

def test_get_performance_summary(db_session):
    """パフォーマンスサマリー計算のテスト"""
    # テスト用の取引データを作成
    base_time = datetime.utcnow()
    
    trades_data = [
        schemas.ActualTradeCreate(
            trade_time=base_time - timedelta(hours=2),
            pair="USDJPY", action="BUY", entry_price=150.0, exit_price=150.5,
            amount=10000, profit_loss=500.0
        ),
        schemas.ActualTradeCreate(
            trade_time=base_time - timedelta(hours=1),
            pair="EURJPY", action="SELL", entry_price=160.0, exit_price=159.5,
            amount=10000, profit_loss=500.0
        ),
        schemas.ActualTradeCreate(
            trade_time=base_time - timedelta(minutes=30),
            pair="GBPJPY", action="BUY", entry_price=185.0, exit_price=184.0,
            amount=10000, profit_loss=-1000.0
        )
    ]
    
    for trade_data in trades_data:
        crud.create_actual_trade(db_session, trade_data)
    
    # パフォーマンスサマリーを計算
    start_date = base_time - timedelta(days=1)
    end_date = base_time
    
    summary = crud.get_performance_summary(db_session, start_date, end_date)
    
    assert summary["total_trades"] == 3
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    assert summary["win_rate"] == pytest.approx(66.67, rel=1e-2)
    assert summary["total_profit_loss"] == 0.0  # 500 + 500 - 1000
    assert summary["profit_factor"] == 0.5  # 1000 / 1000

def test_get_evaluations_in_period(db_session):
    """期間内評価取得のテスト"""
    base_time = datetime.utcnow()
    
    # 推論を作成
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="period_test_ts",
        inference_time=base_time - timedelta(hours=1),
        prompt="Period test prompt",
        raw_response="Period test response",
        inferred_actions=[]
    )
    inference = crud.create_trade_inference(db_session, inference_data)
    
    # 評価を作成
    evaluation_data = schemas.TradeEvaluationCreate(
        inference_id=inference.id,
        logic_evaluation_score=3,
        logic_evaluation_comment="Average analysis",
        potential_profit_loss=100.0,
        evaluation_summary="Period test evaluation"
    )
    crud.create_trade_evaluation(db_session, evaluation_data)
    
    # 期間内評価を取得
    start_date = base_time - timedelta(hours=2)
    end_date = base_time
    
    evaluations = crud.get_evaluations_in_period(db_session, start_date, end_date)
    
    assert len(evaluations) == 1
    assert evaluations[0].inference_id == inference.id
