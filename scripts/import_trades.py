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
                trade_data = json.load(f)
            
            logger.info(f"Loaded {len(trade_data)} trade records from JSON")
            
        except Exception as e:
            logger.error(f"Failed to read JSON file: {e}")
            return 0
        
        # データベースにインポート
        db = SessionLocal()
        imported_count = 0
        
        try:
            for trade_record in trade_data:
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
                        
                        if imported_count % 10 == 0:
                            logger.info(f"Imported {imported_count} trades...")
                            
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
            # 時刻の解析（複数のフォーマットに対応）
            trade_time = self._parse_datetime(record.get('timestamp') or record.get('time') or record.get('date'))
            
            # 通貨ペアの正規化
            pair = self._normalize_currency_pair(record.get('pair') or record.get('symbol') or record.get('currency_pair'))
            
            # アクションの正規化
            action = self._normalize_action(record.get('action') or record.get('side') or record.get('type'))
            
            # 価格データの取得
            entry_price = float(record.get('entry_price') or record.get('open_price') or record.get('price') or 0)
            exit_price = record.get('exit_price') or record.get('close_price')
            if exit_price is not None:
                exit_price = float(exit_price)
            
            # 数量と損益
            amount = float(record.get('amount') or record.get('volume') or record.get('size') or 1)
            profit_loss = record.get('profit_loss') or record.get('pnl') or record.get('profit')
            if profit_loss is not None:
                profit_loss = float(profit_loss)
            
            return schemas.ActualTradeCreate(
                trade_time=trade_time,
                pair=pair,
                action=action,
                entry_price=entry_price,
                exit_price=exit_price,
                amount=amount,
                profit_loss=profit_loss
            )
            
        except Exception as e:
            logger.error(f"Failed to normalize trade record: {e}")
            return None
    
    def _parse_datetime(self, date_str: str) -> datetime:
        """
        様々な日時フォーマットに対応した日時解析
        """
        if not date_str:
            return datetime.utcnow()
        
        # 試行する日時フォーマット
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y/%m/%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%d',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Unix timestampとして解析を試行
        try:
            if isinstance(date_str, (int, float)) or date_str.isdigit():
                return datetime.fromtimestamp(float(date_str))
        except:
            pass
        
        logger.warning(f"Could not parse datetime: {date_str}, using current time")
        return datetime.utcnow()
    
    def _normalize_currency_pair(self, pair_str: str) -> str:
        """
        通貨ペア文字列を正規化
        """
        if not pair_str:
            return "UNKNOWN"
        
        # 一般的な区切り文字を除去して6文字の通貨ペアに変換
        clean_pair = pair_str.replace('/', '').replace('-', '').replace('_', '').upper()
        
        # 6文字の通貨ペア形式になっているかチェック
        if len(clean_pair) == 6 and clean_pair.isalpha():
            return clean_pair
        
        logger.warning(f"Invalid currency pair format: {pair_str}, normalized to: {clean_pair}")
        return clean_pair[:6] if len(clean_pair) >= 6 else "UNKNOWN"
    
    def _normalize_action(self, action_str: str) -> str:
        """
        取引アクションを正規化
        """
        if not action_str:
            return "UNKNOWN"
        
        action_lower = action_str.lower().strip()
        
        if action_lower in ['buy', 'long', '買い', 'ロング']:
            return "BUY"
        elif action_lower in ['sell', 'short', '売り', 'ショート']:
            return "SELL"
        
        logger.warning(f"Unknown action: {action_str}, defaulting to BUY")
        return "BUY"
    
    def _find_matching_inference(self, db: Session, trade_time: datetime, window_hours: int = 2) -> int:
        """
        取引時刻に最も近い推論IDを検索
        """
        try:
            closest_inference = crud.find_closest_inference_for_trade(db, trade_time, window_hours)
            return closest_inference.id if closest_inference else None
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
