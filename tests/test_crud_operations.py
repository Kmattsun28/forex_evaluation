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
        slack_message_ts="test_ts_123", inference_time=datetime.utcnow(),
        prompt="Test prompt for USDJPY", raw_response="I recommend BUY USDJPY based on technical analysis",
        inferred_actions=[{"action": "BUY", "pair": "USDJPY", "confidence": 0.8}]
    )
    created_inference = crud.create_trade_inference(db_session, inference_data)
    assert created_inference.id is not None
    assert created_inference.slack_message_ts == inference_data.slack_message_ts

def test_get_trade_inference(db_session):
    """推論取得のテスト"""
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="get_test_ts", inference_time=datetime.utcnow(),
        prompt="Get test prompt", raw_response="Get test response", inferred_actions=[]
    )
    created = crud.create_trade_inference(db_session, inference_data)
    retrieved = crud.get_trade_inference(db_session, created.id)
    assert retrieved is not None and retrieved.id == created.id

def test_get_trade_inference_by_slack_ts(db_session):
    """Slackタイムスタンプによる推論取得のテスト"""
    inference_data = schemas.TradeInferenceCreate(
        slack_message_ts="slack_ts_test", inference_time=datetime.utcnow(),
        prompt="Slack TS test prompt", raw_response="Slack TS test response", inferred_actions=[]
    )
    created = crud.create_trade_inference(db_session, inference_data)
    retrieved = crud.get_trade_inference_by_slack_ts(db_session, "slack_ts_test")
    assert retrieved is not None and retrieved.id == created.id

def test_create_actual_trade(db_session):
    """実績取引作成のテスト"""
    trade_data = schemas.ActualTradeCreate(
        trade_time=datetime.utcnow(), pair="USDJPY", action="BUY",
        entry_price=150.25, exit_price=150.75, amount=10000, profit_loss=500.0
    )
    created_trade = crud.create_actual_trade(db_session, trade_data)
    assert created_trade.id is not None and created_trade.pair == trade_data.pair

def test_find_closest_inference_for_trade(db_session):
    """取引に最も近い推論の検索テスト"""
    base_time = datetime.utcnow()
    inference1 = crud.create_trade_inference(db_session, schemas.TradeInferenceCreate(
        slack_message_ts="closest_test_1", inference_time=base_time - timedelta(hours=1),
        prompt="p1", raw_response="r1", inferred_actions=[]
    ))
    inference2 = crud.create_trade_inference(db_session, schemas.TradeInferenceCreate(
        slack_message_ts="closest_test_2", inference_time=base_time + timedelta(minutes=30),
        prompt="p2", raw_response="r2", inferred_actions=[]
    ))
    closest = crud.find_closest_inference_for_trade(db_session, base_time, time_window_hours=2)
    assert closest is not None and closest.id == inference2.id

def test_create_trade_evaluation(db_session):
    """評価作成のテスト"""
    inference = crud.create_trade_inference(db_session, schemas.TradeInferenceCreate(
        slack_message_ts="eval_test_ts", inference_time=datetime.utcnow(),
        prompt="p_eval", raw_response="r_eval", inferred_actions=[]
    ))
    evaluation_data = schemas.TradeEvaluationCreate(
        inference_id=inference.id, logic_evaluation_score=4,
        logic_evaluation_comment="Good analysis", potential_profit_loss=250.0,
        evaluation_summary="Solid inference"
    )
    created_evaluation = crud.create_trade_evaluation(db_session, evaluation_data)
    assert created_evaluation.id is not None and created_evaluation.inference_id == inference.id

def test_get_performance_summary(db_session):
    """パフォーマンスサマリー計算のテスト"""
    base_time = datetime.utcnow()
    trades_data = [
        schemas.ActualTradeCreate(trade_time=base_time - timedelta(hours=2), pair="USDJPY", action="BUY", entry_price=150.0, exit_price=150.5, amount=10000, profit_loss=500.0),
        schemas.ActualTradeCreate(trade_time=base_time - timedelta(hours=1), pair="EURJPY", action="SELL", entry_price=160.0, exit_price=159.5, amount=10000, profit_loss=500.0),
        schemas.ActualTradeCreate(trade_time=base_time - timedelta(minutes=30), pair="GBPJPY", action="BUY", entry_price=185.0, exit_price=184.0, amount=10000, profit_loss=-1000.0)
    ]
    for trade_data in trades_data:
        crud.create_actual_trade(db_session, trade_data)
    
    summary = crud.get_performance_summary(db_session, base_time - timedelta(days=1), base_time)
    
    assert summary["total_trades"] == 3
    assert summary["winning_trades"] == 2
    assert summary["losing_trades"] == 1
    assert summary["win_rate"] == pytest.approx(66.67, rel=1e-2)
    assert summary["total_profit_loss"] == 0.0
    assert summary["profit_factor"] == 1.0  # 1000 / 1000 = 1.0

def test_get_evaluations_in_period(db_session):
    """期間内評価取得のテスト"""
    base_time = datetime.utcnow()
    inference = crud.create_trade_inference(db_session, schemas.TradeInferenceCreate(
        slack_message_ts="period_test_ts", inference_time=base_time - timedelta(hours=1),
        prompt="p_period", raw_response="r_period", inferred_actions=[]
    ))
    crud.create_trade_evaluation(db_session, schemas.TradeEvaluationCreate(
        inference_id=inference.id, logic_evaluation_score=3,
        logic_evaluation_comment="Average", potential_profit_loss=100.0,
        evaluation_summary="Period test"
    ))
    evaluations = crud.get_evaluations_in_period(db_session, base_time - timedelta(hours=2), base_time)
    assert len(evaluations) == 1 and evaluations[0].inference_id == inference.id