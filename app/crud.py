# app/crud.py

from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func  # 'func' をインポート

from . import models, schemas

# --- TradeInference CRUD操作 ---

def create_trade_inference(db: Session, inference: schemas.TradeInferenceCreate) -> models.TradeInference:
    """新しい推論レコードを作成"""
    db_inference = models.TradeInference(**inference.model_dump())
    db.add(db_inference)
    db.commit()
    db.refresh(db_inference)
    return db_inference

def get_trade_inference(db: Session, inference_id: int) -> Optional[models.TradeInference]:
    """指定IDの推論レコードを取得"""
    return db.query(models.TradeInference).filter(models.TradeInference.id == inference_id).first()

def get_trade_inference_by_slack_ts(db: Session, slack_ts: str) -> Optional[models.TradeInference]:
    """Slackメッセージタイムスタンプで推論レコードを取得"""
    return db.query(models.TradeInference).filter(models.TradeInference.slack_message_ts == slack_ts).first()

def get_inference_by_slack_ts(db: Session, slack_ts: str) -> Optional[models.TradeInference]:
    """Slackメッセージタイムスタンプで推論レコードを取得（エイリアス）"""
    return get_trade_inference_by_slack_ts(db, slack_ts)

def get_trade_inferences(db: Session, skip: int = 0, limit: int = 100) -> List[models.TradeInference]:
    """推論レコード一覧を取得"""
    return db.query(models.TradeInference).offset(skip).limit(limit).all()

# --- ActualTrade CRUD操作 ---

def create_actual_trade(db: Session, trade: schemas.ActualTradeCreate) -> models.ActualTrade:
    """新しい実績取引レコードを作成"""
    db_trade = models.ActualTrade(**trade.model_dump())
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade

def get_actual_trade(db: Session, trade_id: int) -> Optional[models.ActualTrade]:
    """指定IDの実績取引レコードを取得"""
    return db.query(models.ActualTrade).filter(models.ActualTrade.id == trade_id).first()

def get_actual_trades_by_inference(db: Session, inference_id: int) -> List[models.ActualTrade]:
    """指定推論IDに関連する実績取引一覧を取得"""
    return db.query(models.ActualTrade).filter(models.ActualTrade.inference_id == inference_id).all()

def find_closest_inference_for_trade(db: Session, trade_time: datetime, time_window_hours: int = 2) -> Optional[models.TradeInference]:
    """取引時刻に最も近い推論を検索（時間窓内）"""
    start_time = trade_time - timedelta(hours=time_window_hours)
    end_time = trade_time + timedelta(hours=time_window_hours)

    return db.query(models.TradeInference).filter(
        and_(
            models.TradeInference.inference_time >= start_time,
            models.TradeInference.inference_time <= end_time
        )
    ).order_by(
        # Pythonのabs()ではなく、SQLAlchemyのfunc.abs()を使用
        func.abs(models.TradeInference.inference_time - trade_time)
    ).first()

# 【ここから追加】
def get_actual_trade_by_details(db: Session, trade_time: datetime, pair: str, action: str, entry_price: float, amount: float) -> Optional[models.ActualTrade]:
    """取引の詳細情報を使って、既存の取引レコードを検索する"""
    return db.query(models.ActualTrade).filter(
        and_(
            models.ActualTrade.trade_time == trade_time,
            models.ActualTrade.pair == pair,
            models.ActualTrade.action == action,
            models.ActualTrade.entry_price == entry_price,
            models.ActualTrade.amount == amount
        )
    ).first()
# 【ここまで追加】

# --- TradeEvaluation CRUD操作 ---

def create_trade_evaluation(db: Session, evaluation: schemas.TradeEvaluationCreate) -> models.TradeEvaluation:
    """新しい評価レコードを作成"""
    db_evaluation = models.TradeEvaluation(**evaluation.model_dump())
    db.add(db_evaluation)
    db.commit()
    db.refresh(db_evaluation)
    return db_evaluation

def get_trade_evaluation(db: Session, evaluation_id: int) -> Optional[models.TradeEvaluation]:
    """指定IDの評価レコードを取得"""
    return db.query(models.TradeEvaluation).filter(models.TradeEvaluation.id == evaluation_id).first()

def get_trade_evaluation_by_inference(db: Session, inference_id: int) -> Optional[models.TradeEvaluation]:
    """指定推論IDの評価レコードを取得"""
    return db.query(models.TradeEvaluation).filter(models.TradeEvaluation.inference_id == inference_id).first()

# --- レポート用のデータ取得 ---

def get_evaluations_in_period(db: Session, start_date: datetime, end_date: datetime) -> List[models.TradeEvaluation]:
    """指定期間内の評価レコードとその関連データを取得"""
    return db.query(models.TradeEvaluation).join(models.TradeInference).filter(
        and_(
            models.TradeInference.inference_time >= start_date,
            models.TradeInference.inference_time <= end_date
        )
    ).all()

def get_performance_summary(db: Session, start_date: datetime, end_date: datetime) -> dict:
    """指定期間のパフォーマンスサマリーを計算"""
    # 期間内の実績取引を取得
    trades = db.query(models.ActualTrade).filter(
        and_(
            models.ActualTrade.trade_time >= start_date,
            models.ActualTrade.trade_time <= end_date,
            models.ActualTrade.profit_loss.isnot(None)  # 決済済みの取引のみ
        )
    ).all()

    if not trades:
        return {
            "total_trades": 0, "winning_trades": 0, "losing_trades": 0, "win_rate": 0.0,
            "total_profit_loss": 0.0, "average_profit": 0.0, "average_loss": 0.0, "profit_factor": 0.0
        }

    # 統計計算
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t.profit_loss > 0])
    losing_trades = len([t for t in trades if t.profit_loss < 0])
    total_profit_loss = sum(t.profit_loss for t in trades)
    profits = [t.profit_loss for t in trades if t.profit_loss > 0]
    losses = [t.profit_loss for t in trades if t.profit_loss < 0]
    average_profit = sum(profits) / len(profits) if profits else 0.0
    average_loss = sum(losses) / len(losses) if losses else 0.0
    total_profits = sum(profits)
    total_losses = abs(sum(losses))
    profit_factor = total_profits / total_losses if total_losses > 0 else float('inf')

    return {
        "total_trades": total_trades, "winning_trades": winning_trades, "losing_trades": losing_trades,
        "win_rate": winning_trades / total_trades * 100 if total_trades > 0 else 0.0,
        "total_profit_loss": total_profit_loss, "average_profit": average_profit,
        "average_loss": average_loss, "profit_factor": profit_factor
    }