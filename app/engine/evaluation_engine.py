# app/engine/evaluation_engine.py

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from ..models import TradeInference, ActualTrade
from .. import schemas

class EvaluationEngine:
    """
    取引推論を評価するエンジン
    推論の妥当性とパフォーマンスを分析する
    """
    
    def __init__(self):
        self.evaluation_criteria = {
            'logic_score_weights': {
                'market_analysis': 0.3,
                'technical_indicators': 0.25,
                'risk_management': 0.25,
                'reasoning_clarity': 0.2
            }
        }
    
    def evaluate_inference(
        self, 
        inference: TradeInference, 
        actual_trades: List[ActualTrade] = None
    ) -> schemas.TradeEvaluationCreate:
        """
        推論を総合的に評価する
        
        Args:
            inference: 評価対象の推論
            actual_trades: 関連する実績取引（あれば）
            
        Returns:
            評価結果のスキーマ
        """
        # 1. ロジックの妥当性を評価
        logic_score, logic_comment = self._evaluate_logic(inference)
        
        # 2. ポテンシャル損益を計算（仮想取引）
        potential_pnl = self._calculate_potential_profit_loss(inference)
        
        # 3. 実績がある場合の実損益分析
        actual_pnl_analysis = ""
        if actual_trades:
            actual_pnl_analysis = self._analyze_actual_performance(actual_trades)
        
        # 4. 総合評価サマリーを生成
        evaluation_summary = self._generate_evaluation_summary(
            inference, logic_score, potential_pnl, actual_trades, actual_pnl_analysis
        )
        
        return schemas.TradeEvaluationCreate(
            inference_id=inference.id,
            logic_evaluation_score=logic_score,
            logic_evaluation_comment=logic_comment,
            potential_profit_loss=potential_pnl,
            evaluation_summary=evaluation_summary
        )
    
    def _evaluate_logic(self, inference: TradeInference) -> tuple[int, str]:
        """
        推論のロジックを評価する
        
        Returns:
            (score: 1-5, comment: str)
        """
        prompt = inference.prompt.lower()
        response = inference.raw_response.lower()
        
        score = 1  # 基底スコア
        comments = []
        
        # 市場分析の深度をチェック
        market_keywords = [
            'trend', 'support', 'resistance', 'volume', 'momentum',
            'トレンド', 'サポート', 'レジスタンス', '出来高', '勢い'
        ]
        market_analysis_count = sum(1 for keyword in market_keywords if keyword in response)
        
        if market_analysis_count >= 3:
            score += 1
            comments.append("市場分析が十分に行われている")
        elif market_analysis_count >= 1:
            comments.append("基本的な市場分析が含まれている")
        else:
            comments.append("市場分析が不十分")
        
        # テクニカル指標の使用をチェック
        technical_keywords = [
            'rsi', 'macd', 'moving average', 'bollinger', 'ema', 'sma',
            'adx', 'stochastic', '移動平均', 'ボリンジャー'
        ]
        technical_count = sum(1 for keyword in technical_keywords if keyword in response)
        
        if technical_count >= 2:
            score += 1
            comments.append("複数のテクニカル指標を考慮している")
        elif technical_count >= 1:
            comments.append("テクニカル指標を考慮している")
        else:
            comments.append("テクニカル指標の言及が不足")
        
        # リスク管理の言及をチェック
        risk_keywords = [
            'stop loss', 'risk', 'position size', 'drawdown',
            'ストップロス', 'リスク', 'ポジションサイズ', 'ドローダウン'
        ]
        risk_count = sum(1 for keyword in risk_keywords if keyword in response)
        
        if risk_count >= 2:
            score += 1
            comments.append("リスク管理が十分に考慮されている")
        elif risk_count >= 1:
            comments.append("基本的なリスク管理が考慮されている")
        else:
            comments.append("リスク管理の言及が不足")
        
        # 推論の明確性をチェック
        if len(response) >= 200 and ('because' in response or 'なぜなら' in response or 'ため' in response):
            score += 1
            comments.append("推論の根拠が明確に説明されている")
        elif len(response) >= 100:
            comments.append("推論の説明が含まれている")
        else:
            comments.append("推論の説明が不十分")
        
        # スコアを1-5の範囲に正規化
        score = min(5, max(1, score))
        
        return score, "; ".join(comments)
    
    def _calculate_potential_profit_loss(self, inference: TradeInference) -> float:
        """
        仮想取引での潜在的損益を計算する（簡易版）
        
        Returns:
            潜在損益（仮想的な計算）
        """
        # 【未実装・簡易版】: 現在は推論の強度と市場の典型的な変動を基に概算しています。
        # 本格的な実装では、この関数内で推論時点から数時間後の実際の価格データを
        # データベースから取得し、それと比較して仮想的な損益を計算する必要があります。
        
        if not inference.inferred_actions:
            return 0.0
        
        actions = inference.inferred_actions
        if not actions or len(actions) == 0:
            return 0.0
        
        first_action = actions[0]
        confidence = first_action.get('confidence', 0.5)
        base_return = 0.01
        potential_return = base_return * confidence
        risk_adjustment = 0.8
        
        return potential_return * risk_adjustment * 10000

    def _analyze_actual_performance(self, actual_trades: List[ActualTrade]) -> str:
        """
        実績取引のパフォーマンスを分析
        
        Returns:
            分析結果の文字列
        """
        if not actual_trades:
            return "関連する実績取引がありません"
        
        total_pnl = sum(trade.profit_loss for trade in actual_trades if trade.profit_loss is not None)
        completed_trades = [trade for trade in actual_trades if trade.profit_loss is not None]
        
        if not completed_trades:
            return f"実行された取引数: {len(actual_trades)}件（未決済）"
        
        winning_trades = len([trade for trade in completed_trades if trade.profit_loss > 0])
        win_rate = winning_trades / len(completed_trades) * 100
        
        return f"実行取引: {len(actual_trades)}件, 決済済み: {len(completed_trades)}件, " \
               f"勝率: {win_rate:.1f}%, 総損益: {total_pnl:.2f}"
    
    def _generate_evaluation_summary(
        self, 
        inference: TradeInference, 
        logic_score: int, 
        potential_pnl: float,
        actual_trades: List[ActualTrade],
        actual_analysis: str
    ) -> str:
        """
        総合評価サマリーを生成
        """
        summary_parts = []
        
        # ロジック評価
        if logic_score >= 4:
            summary_parts.append("推論ロジックは優秀")
        elif logic_score >= 3:
            summary_parts.append("推論ロジックは良好")
        else:
            summary_parts.append("推論ロジックに改善の余地あり")
        
        # ポテンシャル評価
        if potential_pnl > 50:
            summary_parts.append("高い利益ポテンシャル")
        elif potential_pnl > 0:
            summary_parts.append("正の利益ポテンシャル")
        else:
            summary_parts.append("リスクを伴う推論")
        
        # 実績評価
        if actual_trades:
            summary_parts.append(f"実績: {actual_analysis}")
        
        # 改善提案
        if logic_score < 3:
            summary_parts.append("市場分析とリスク管理の強化を推奨")
        
        return ". ".join(summary_parts) + "."