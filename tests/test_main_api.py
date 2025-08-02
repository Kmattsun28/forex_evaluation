# tests/test_main_api.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.database import get_db
from app.models import Base

# テスト用のインメモリSQLiteデータベース
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    """テスト用のデータベースセッションを提供"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# 依存性を上書き
app.dependency_overrides[get_db] = override_get_db

# テストクライアントを作成
client = TestClient(app)

@pytest.fixture(scope="module")
def setup_database():
    """テスト用データベースのセットアップ"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_read_root(setup_database):
    """ルートエンドポイントのテスト"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Forex Trading Evaluation System"
    assert data["version"] == "2.3.0"
    assert data["status"] == "running"

def test_health_check(setup_database):
    """ヘルスチェックエンドポイントのテスト"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_create_inference(setup_database):
    """推論作成エンドポイントのテスト"""
    inference_data = {
        "slack_message_ts": "1234567890.123456",
        "inference_time": "2024-01-01T10:00:00",
        "prompt": "Test prompt for USDJPY analysis",
        "raw_response": "Based on analysis, I recommend BUY USDJPY",
        "inferred_actions": [{"action": "BUY", "pair": "USDJPY", "confidence": 0.8}]
    }
    
    response = client.post("/inferences/", json=inference_data)
    assert response.status_code == 200
    data = response.json()
    assert data["slack_message_ts"] == inference_data["slack_message_ts"]
    assert data["prompt"] == inference_data["prompt"]

def test_create_duplicate_inference(setup_database):
    """重複推論作成のテスト"""
    inference_data = {
        "slack_message_ts": "duplicate_test_ts",
        "inference_time": "2024-01-01T10:00:00",
        "prompt": "Test prompt",
        "raw_response": "Test response",
        "inferred_actions": []
    }
    
    # 最初の作成は成功
    response1 = client.post("/inferences/", json=inference_data)
    assert response1.status_code == 200
    
    # 重複作成は失敗
    response2 = client.post("/inferences/", json=inference_data)
    assert response2.status_code == 400

def test_get_inferences(setup_database):
    """推論一覧取得のテスト"""
    response = client.get("/inferences/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_create_trade(setup_database):
    """取引作成エンドポイントのテスト"""
    trade_data = {
        "trade_time": "2024-01-01T10:30:00",
        "pair": "USDJPY",
        "action": "BUY",
        "entry_price": 150.25,
        "exit_price": 150.75,
        "amount": 10000,
        "profit_loss": 500.0
    }
    
    response = client.post("/trades/", json=trade_data)
    assert response.status_code == 200
    data = response.json()
    assert data["pair"] == trade_data["pair"]
    assert data["action"] == trade_data["action"]

def test_get_performance_summary(setup_database):
    """パフォーマンスサマリー取得のテスト"""
    response = client.get("/reports/summary?period=daily")
    assert response.status_code == 200
    data = response.json()
    assert "period" in data
    assert "total_trades" in data
    assert "win_rate" in data

def test_invalid_period_parameter(setup_database):
    """無効なperiodパラメータのテスト"""
    response = client.get("/reports/summary?period=invalid")
    assert response.status_code == 422  # バリデーションエラー

def test_scheduler_status(setup_database):
    """スケジューラーステータスのテスト"""
    response = client.get("/scheduler/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "jobs" in data
