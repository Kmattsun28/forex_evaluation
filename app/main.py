# app/main.py

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import get_db, create_tables
from .scheduler import start_scheduler, stop_scheduler, get_scheduler

# FastAPIアプリケーションの初期化
app = FastAPI(
    title="Forex Trading Evaluation System",
    description="為替取引評価システム - 推論ログの収集・評価・レポート生成",
    version="2.3.0"
)

# アプリケーション起動時にテーブルを作成
@app.on_event("startup")
def startup_event():
    create_tables()
    # スケジューラーを開始
    start_scheduler()

@app.on_event("shutdown")
def shutdown_event():
    # スケジューラーを停止
    stop_scheduler()

# --- 基本的なヘルスチェック ---

@app.get("/")
def read_root():
    """システムの基本情報を返す"""
    return {
        "message": "Forex Trading Evaluation System",
        "version": "2.3.0",
        "status": "running"
    }

@app.get("/health")
def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# --- 推論関連エンドポイント ---

@app.post("/inferences/", response_model=schemas.TradeInference)
def create_inference(
    inference: schemas.TradeInferenceCreate,
    db: Session = Depends(get_db)
):
    """新しい推論レコードを作成"""
    # 既存のSlackメッセージタイムスタンプをチェック
    existing = crud.get_trade_inference_by_slack_ts(db, inference.slack_message_ts)
    if existing:
        raise HTTPException(status_code=400, detail="Inference with this Slack timestamp already exists")
    
    return crud.create_trade_inference(db=db, inference=inference)

@app.get("/inferences/", response_model=List[schemas.TradeInference])
def read_inferences(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """推論レコード一覧を取得"""
    return crud.get_trade_inferences(db, skip=skip, limit=limit)

@app.get("/inferences/{inference_id}", response_model=schemas.TradeInference)
def read_inference(inference_id: int, db: Session = Depends(get_db)):
    """指定IDの推論レコードを取得"""
    inference = crud.get_trade_inference(db, inference_id=inference_id)
    if inference is None:
        raise HTTPException(status_code=404, detail="Inference not found")
    return inference

# --- 実績取引関連エンドポイント ---

@app.post("/trades/", response_model=schemas.ActualTrade)
def create_trade(
    trade: schemas.ActualTradeCreate,
    db: Session = Depends(get_db)
):
    """新しい実績取引レコードを作成"""
    return crud.create_actual_trade(db=db, trade=trade)

@app.get("/trades/inference/{inference_id}", response_model=List[schemas.ActualTrade])
def read_trades_by_inference(inference_id: int, db: Session = Depends(get_db)):
    """指定推論IDに関連する実績取引一覧を取得"""
    return crud.get_actual_trades_by_inference(db, inference_id=inference_id)

# --- 評価関連エンドポイント ---

@app.post("/evaluations/", response_model=schemas.TradeEvaluation)
def create_evaluation(
    evaluation: schemas.TradeEvaluationCreate,
    db: Session = Depends(get_db)
):
    """新しい評価レコードを作成"""
    # 推論の存在確認
    inference = crud.get_trade_inference(db, evaluation.inference_id)
    if not inference:
        raise HTTPException(status_code=404, detail="Inference not found")
    
    # 既存の評価をチェック
    existing = crud.get_trade_evaluation_by_inference(db, evaluation.inference_id)
    if existing:
        raise HTTPException(status_code=400, detail="Evaluation for this inference already exists")
    
    return crud.create_trade_evaluation(db=db, evaluation=evaluation)

@app.get("/evaluations/{inference_id}", response_model=schemas.TradeEvaluation)
def read_evaluation(inference_id: int, db: Session = Depends(get_db)):
    """指定推論IDの評価結果を取得"""
    evaluation = crud.get_trade_evaluation_by_inference(db, inference_id=inference_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation

# --- レポート関連エンドポイント ---

@app.get("/reports/summary", response_model=schemas.PerformanceSummary)
def get_performance_summary(
    period: str = Query(..., regex="^(daily|weekly|all_time)$"),
    db: Session = Depends(get_db)
):
    """指定期間のパフォーマンスサマリーを取得"""
    now = datetime.utcnow()
    
    if period == "daily":
        start_date = now - timedelta(days=1)
        end_date = now
    elif period == "weekly":
        start_date = now - timedelta(days=7)
        end_date = now
    elif period == "all_time":
        start_date = datetime(2020, 1, 1)  # 十分に過去の日付
        end_date = now
    else:
        raise HTTPException(status_code=400, detail="Invalid period")
    
    # パフォーマンス統計を計算
    summary_data = crud.get_performance_summary(db, start_date, end_date)
    
    return schemas.PerformanceSummary(
        period=period,
        start_date=start_date,
        end_date=end_date,
        **summary_data
    )

@app.get("/reports/evaluations", response_model=List[schemas.EvaluationDetails])
def get_evaluation_details(
    period: str = Query("daily", regex="^(daily|weekly|all_time)$"),
    db: Session = Depends(get_db)
):
    """指定期間の評価詳細一覧を取得"""
    now = datetime.utcnow()
    
    if period == "daily":
        start_date = now - timedelta(days=1)
        end_date = now
    elif period == "weekly":
        start_date = now - timedelta(days=7)
        end_date = now
    elif period == "all_time":
        start_date = datetime(2020, 1, 1)
        end_date = now
    
    evaluations = crud.get_evaluations_in_period(db, start_date, end_date)
    
    result = []
    for eval_record in evaluations:
        trades = crud.get_actual_trades_by_inference(db, eval_record.inference_id)
        result.append(schemas.EvaluationDetails(
            inference=eval_record.inference,
            evaluation=eval_record,
            actual_trades=trades
        ))
    
    return result

# --- スケジューラー管理エンドポイント ---

@app.get("/scheduler/status")
def get_scheduler_status():
    """スケジューラーのステータスを取得"""
    scheduler = get_scheduler()
    return {
        "status": "running",
        "jobs": scheduler.get_job_status()
    }
