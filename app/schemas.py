# app/schemas.py

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

# --- 基本的なレスポンスモデル ---

class BaseResponse(BaseModel):
    class Config:
        from_attributes = True

# --- 推論関連スキーマ ---

class TradeInferenceBase(BaseModel):
    slack_message_ts: str
    inference_time: datetime
    prompt: str
    raw_response: str
    inferred_actions: Optional[List[Dict[str, Any]]] = None

class TradeInferenceCreate(TradeInferenceBase):
    pass

class TradeInference(TradeInferenceBase, BaseResponse):
    id: int

# --- 実績取引関連スキーマ ---

class ActualTradeBase(BaseModel):
    trade_time: datetime
    pair: str
    action: str
    entry_price: float
    exit_price: Optional[float] = None
    amount: float
    profit_loss: Optional[float] = None

class ActualTradeCreate(ActualTradeBase):
    inference_id: Optional[int] = None

class ActualTrade(ActualTradeBase, BaseResponse):
    id: int
    inference_id: Optional[int] = None

# --- 評価関連スキーマ ---

class TradeEvaluationBase(BaseModel):
    logic_evaluation_score: Optional[int] = None
    logic_evaluation_comment: Optional[str] = None
    potential_profit_loss: Optional[float] = None
    evaluation_summary: Optional[str] = None

class TradeEvaluationCreate(TradeEvaluationBase):
    inference_id: int

class TradeEvaluation(TradeEvaluationBase, BaseResponse):
    id: int
    inference_id: int
    evaluation_time: datetime

# --- レポート関連スキーマ ---

class PerformanceSummary(BaseModel):
    period: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit_loss: float
    average_profit: float
    average_loss: float
    profit_factor: float
    start_date: datetime
    end_date: datetime

class EvaluationDetails(BaseModel):
    inference: TradeInference
    evaluation: Optional[TradeEvaluation] = None
    actual_trades: List[ActualTrade] = []
