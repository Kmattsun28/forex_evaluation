# scripts/run_evaluation.py

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, create_tables
from app import crud, schemas
from app.engine.evaluation_engine import EvaluationEngine

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EvaluationRunner:
    """
    推論の評価を実行するクラス
    """
    
    def __init__(self):
        self.evaluation_engine = EvaluationEngine()
    
    def run_evaluations(self, max_evaluations: int = 100) -> int:
        """
        未評価の推論に対して評価を実行
        
        Args:
            max_evaluations: 一度に評価する最大数
            
        Returns:
            実行した評価の数
        """
        logger.info(f"Starting evaluation run (max: {max_evaluations})")
        
        db = SessionLocal()
        evaluated_count = 0
        
        try:
            # 未評価の推論を取得
            unevaluated_inferences = self._get_unevaluated_inferences(db, max_evaluations)
            logger.info(f"Found {len(unevaluated_inferences)} unevaluated inferences")
            
            for inference in unevaluated_inferences:
                try:
                    # 関連する実績取引を取得
                    actual_trades = crud.get_actual_trades_by_inference(db, inference.id)
                    
                    # 評価を実行
                    evaluation_data = self.evaluation_engine.evaluate_inference(
                        inference, actual_trades
                    )
                    
                    # データベースに保存
                    crud.create_trade_evaluation(db, evaluation_data)
                    evaluated_count += 1
                    
                    logger.info(f"Evaluated inference {inference.id} (score: {evaluation_data.logic_evaluation_score})")
                    
                except Exception as e:
                    logger.error(f"Failed to evaluate inference {inference.id}: {e}")
                    continue
            
            logger.info(f"Successfully completed {evaluated_count} evaluations")
            return evaluated_count
            
        finally:
            db.close()
    
    def _get_unevaluated_inferences(self, db: Session, limit: int) -> List:
        """
        評価が未実施の推論一覧を取得
        """
        # 評価テーブルに存在しない推論IDを取得するサブクエリ
        from sqlalchemy import not_, exists
        from app.models import TradeInference, TradeEvaluation
        
        unevaluated = db.query(TradeInference).filter(
            not_(exists().where(TradeEvaluation.inference_id == TradeInference.id))
        ).order_by(TradeInference.inference_time.desc()).limit(limit).all()
        
        return unevaluated
    
    def re_evaluate_inference(self, inference_id: int) -> bool:
        """
        特定の推論を再評価
        
        Args:
            inference_id: 再評価する推論のID
            
        Returns:
            再評価が成功したかどうか
        """
        logger.info(f"Re-evaluating inference {inference_id}")
        
        db = SessionLocal()
        try:
            # 推論を取得
            inference = crud.get_trade_inference(db, inference_id)
            if not inference:
                logger.error(f"Inference {inference_id} not found")
                return False
            
            # 既存の評価を削除
            existing_evaluation = crud.get_trade_evaluation_by_inference(db, inference_id)
            if existing_evaluation:
                db.delete(existing_evaluation)
                db.commit()
            
            # 関連する実績取引を取得
            actual_trades = crud.get_actual_trades_by_inference(db, inference_id)
            
            # 新しい評価を実行
            evaluation_data = self.evaluation_engine.evaluate_inference(
                inference, actual_trades
            )
            
            # データベースに保存
            crud.create_trade_evaluation(db, evaluation_data)
            
            logger.info(f"Successfully re-evaluated inference {inference_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to re-evaluate inference {inference_id}: {e}")
            return False
        finally:
            db.close()

def main():
    """
    メイン実行関数
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Run trade inference evaluations")
    parser.add_argument(
        '--max-evaluations', 
        type=int, 
        default=100, 
        help='Maximum number of evaluations to run in this session'
    )
    parser.add_argument(
        '--re-evaluate', 
        type=int, 
        help='Re-evaluate a specific inference ID'
    )
    
    args = parser.parse_args()
    
    try:
        # データベーステーブルが存在することを確認
        create_tables()
        
        # 評価ランナーを初期化
        runner = EvaluationRunner()
        
        if args.re_evaluate:
            # 特定の推論を再評価
            success = runner.re_evaluate_inference(args.re_evaluate)
            if success:
                logger.info(f"Re-evaluation completed for inference {args.re_evaluate}")
            else:
                logger.error(f"Re-evaluation failed for inference {args.re_evaluate}")
                sys.exit(1)
        else:
            # 通常の評価実行
            evaluated_count = runner.run_evaluations(args.max_evaluations)
            logger.info(f"Evaluation run completed. Processed: {evaluated_count}")
        
    except Exception as e:
        logger.error(f"Evaluation run failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
