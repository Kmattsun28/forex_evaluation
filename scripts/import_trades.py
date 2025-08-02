# scripts/import_trades.py

import os
import sys
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, create_tables
from app import crud, schemas

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradeImporter:
    """
    取引履歴JSONファイルをデータベースにインポートするクラス
    """
    
    def __init__(self, json_file_path: str = "/app/deal_log/transaction_log.json"):
        self.json_file_path = json_file_path
    
    def import_trades(self) -> int:
        """
        JSONファイルから取引データをインポート
        
        Returns:
            インポートされた取引の数
        """
        logger.info(f"Starting trade import from {self.json_file_path}")
        
        if not os.path.exists(self.json_file_path):
            logger.error(f"Trade data file not found: {self.json_file_path}")
            return 0
        
        # JSONファイルを読み込み
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                trade_data_json = json.load(f)
            
            # "transactions" キーから取引リストを取得
            trade_records = trade_data_json.get("transactions", [])
            
            logger.info(f"Loaded {len(trade_records)} trade records from JSON")
            
        except Exception as e:
            logger.error(f"Failed to read or parse JSON file: {e}")
            return 0
        
        db = SessionLocal()
        imported_count = 0
        
        try:
            for trade_record in trade_records:
                try:
                    # JSONレコードを標準化
                    trade_create = self._normalize_trade_record(trade_record)
                    
                    if trade_create:
                        # 最も近い推論との紐付けを試行
                        inference_id = self._find_matching_inference(db, trade_create.trade_time)
                        if inference_id:
                            trade_create.inference_id = inference_id
                        
                        # データベースに保存
                        crud.create_actual_trade(db, trade_create)
                        imported_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to import trade record {trade_record}: {e}")
                    continue
            
            logger.info(f"Successfully imported {imported_count} trades")
            return imported_count
            
        finally:
            db.close()
    
    def _normalize_trade_record(self, record: Dict[str, Any]) -> schemas.ActualTradeCreate:
        """
        JSONレコードを標準化されたトレードスキーマに変換
        """
        try:
            # amount の正負から action (BUY/SELL) を決定
            amount_val = float(record.get('amount', 0))
            action = "BUY" if amount_val > 0 else "SELL"
            
            # exit_price と profit_loss はこのJSON形式では不明なため、Noneとする
            # amountは常に正の値として記録する
            return schemas.ActualTradeCreate(
                trade_time=self._parse_jp_datetime(record.get('timestamp')),
                pair=record.get('currency_pair'),
                action=action,
                entry_price=float(record.get('rate', 0)),
                exit_price=None,
                amount=abs(amount_val),
                profit_loss=None 
            )
            
        except Exception as e:
            logger.error(f"Failed to normalize trade record: {e}")
            return None
    
    def _parse_jp_datetime(self, date_str: str) -> datetime:
        """
        日本語の日付文字列 "YYYY年MM月DD日" をdatetimeオブジェクトに変換
        """
        if not date_str:
            return datetime.utcnow()
        try:
            # "年", "月", "日" をハイフンに置換してパース
            formatted_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
            return datetime.strptime(formatted_str, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"Could not parse Japanese datetime: {date_str}, using current time")
            return datetime.utcnow()

    def _find_matching_inference(self, db: Session, trade_time: datetime, window_hours: int = 24) -> int:
        """
        取引時刻に最も近い推論IDを検索 (検索範囲を24時間に拡大)
        """
        try:
            closest_inference = crud.find_closest_inference_for_trade(db, trade_time, window_hours)
            if closest_inference:
                logger.info(f"Found matching inference {closest_inference.id} for trade at {trade_time}")
                return closest_inference.id
            return None
        except Exception as e:
            logger.debug(f"Could not find matching inference for trade at {trade_time}: {e}")
            return None

def main():
    """
    メイン実行関数
    """
    try:
        # データベーステーブルが存在することを確認
        create_tables()
        
        # インポーターを初期化
        importer = TradeImporter()
        
        # 取引データをインポート
        imported_count = importer.import_trades()
        
        logger.info(f"Trade import completed. Imported records: {imported_count}")
        
    except Exception as e:
        logger.error(f"Trade import failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()