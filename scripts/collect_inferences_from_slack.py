# scripts/collect_inferences_from_slack.py

import os
import sys
import logging
from datetime import datetime
from typing import List, Optional
import requests

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.database import SessionLocal, create_tables
from app import crud, schemas
from app.engine.inference_engine import InferenceEngine

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SlackInferenceCollector:
    """
    Slackから推論ログを収集するクラス
    """
    
    def __init__(self):
        self.slack_token = os.getenv("SLACK_BOT_TOKEN")
        self.channel_id = os.getenv("SLACK_CHANNEL_ID")
        
        if not self.slack_token or not self.channel_id:
            raise ValueError("SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set in environment variables")
        
        self.client = WebClient(token=self.slack_token)
        self.inference_engine = InferenceEngine()
    
    def collect_new_inferences(self, lookback_hours: int = 24) -> int:
        """
        指定時間内の新しい推論メッセージを収集
        
        Args:
            lookback_hours: 遡る時間（時間単位）
            
        Returns:
            収集した新しい推論の数
        """
        logger.info(f"Starting inference collection for the last {lookback_hours} hours")
        
        # データベースセッションを取得
        db = SessionLocal()
        try:
            # 既存の推論メッセージIDを取得
            existing_ts = self._get_existing_message_timestamps(db)
            logger.info(f"Found {len(existing_ts)} existing inference records")
            
            # Slackからメッセージを取得
            messages = self._fetch_slack_messages(lookback_hours)
            logger.info(f"Fetched {len(messages)} messages from Slack")
            
            new_inferences_count = 0
            
            for message in messages:
                message_ts = message.get('ts')
                
                # 既に処理済みのメッセージはスキップ
                if message_ts in existing_ts:
                    continue
                
                # 推論メッセージとして処理
                inference_data = self._process_message(message)
                if inference_data:
                    try:
                        crud.create_trade_inference(db, inference_data)
                        new_inferences_count += 1
                        logger.info(f"Created new inference record for message {message_ts}")
                    except Exception as e:
                        logger.error(f"Failed to create inference for message {message_ts}: {e}")
            
            logger.info(f"Successfully collected {new_inferences_count} new inferences")
            return new_inferences_count
            
        except Exception as e:
            logger.error(f"Error during inference collection: {e}")
            raise
        finally:
            db.close()
    
    def _get_existing_message_timestamps(self, db: Session) -> set:
        """
        既存の推論レコードのSlackメッセージタイムスタンプを取得
        """
        existing_inferences = crud.get_trade_inferences(db, skip=0, limit=10000)
        return {inf.slack_message_ts for inf in existing_inferences if inf.slack_message_ts}
    
    def _fetch_slack_messages(self, lookback_hours: int) -> List[dict]:
        """
        Slackから指定時間内のメッセージを取得
        """
        try:
            # 現在時刻から指定時間前までのタイムスタンプを計算
            now = datetime.now()
            oldest_timestamp = (now.timestamp() - (lookback_hours * 3600))
            
            response = self.client.conversations_history(
                channel=self.channel_id,
                oldest=str(oldest_timestamp),
                limit=1000
            )
            
            if response["ok"]:
                return response["messages"]
            else:
                logger.error(f"Failed to fetch Slack messages: {response.get('error')}")
                return []
                
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            return []
    
    def _process_message(self, message: dict) -> Optional[schemas.TradeInferenceCreate]:
        """
        Slackメッセージを推論データに変換
        """
        message_ts = message.get('ts')
        message_text = message.get('text', '')
        
        # メッセージがボットからの推論結果かどうかを判定
        if not self._is_inference_message(message_text):
            return None
        
        # メッセージの投稿時刻を取得
        try:
            inference_time = datetime.fromtimestamp(float(message_ts))
        except (ValueError, TypeError):
            logger.warning(f"Invalid timestamp in message: {message_ts}")
            return None
        
        # 添付ファイルからプロンプトを取得
        prompt_content = self._extract_prompt_from_files(message)
        if not prompt_content:
            # プロンプトが見つからない場合は、メッセージテキスト自体をプロンプトとして使用
            prompt_content = "プロンプト情報なし"
        
        # 推論アクションを解析
        inferred_actions = self.inference_engine.parse_inference_response(message_text)
        
        return schemas.TradeInferenceCreate(
            slack_message_ts=message_ts,
            inference_time=inference_time,
            prompt=prompt_content,
            raw_response=message_text,
            inferred_actions=inferred_actions
        )
    
    def _is_inference_message(self, message_text: str) -> bool:
        """
        メッセージが推論結果かどうかを判定
        """
        # 推論メッセージの特徴的なキーワードをチェック
        inference_keywords = [
            'buy', 'sell', 'ポジション', '推奨', '取引',
            'usdjpy', 'eurjpy', 'gbpjpy', 'audjpy',
            'analysis', '分析', 'trend', 'トレンド'
        ]
        
        message_lower = message_text.lower()
        return any(keyword in message_lower for keyword in inference_keywords)
    
    def _extract_prompt_from_files(self, message: dict) -> Optional[str]:
        """
        メッセージの添付ファイルからプロンプト内容を取得
        """
        files = message.get('files', [])
        
        for file_info in files:
            # テキストファイルのみを処理
            if file_info.get('mimetype') == 'text/plain' or file_info.get('name', '').endswith('.txt'):
                file_url = file_info.get('url_private')
                if file_url:
                    try:
                        # Slackのファイルをダウンロード
                        headers = {'Authorization': f'Bearer {self.slack_token}'}
                        response = requests.get(file_url, headers=headers)
                        
                        if response.status_code == 200:
                            return response.text
                        else:
                            logger.warning(f"Failed to download file {file_url}: {response.status_code}")
                    except Exception as e:
                        logger.error(f"Error downloading file {file_url}: {e}")
        
        return None

def main():
    """
    メイン実行関数
    """
    try:
        # データベーステーブルが存在することを確認
        create_tables()
        
        # Slack収集器を初期化
        collector = SlackInferenceCollector()
        
        # 新しい推論を収集（過去24時間）
        new_count = collector.collect_new_inferences(lookback_hours=24)
        
        logger.info(f"Inference collection completed. New records: {new_count}")
        
    except Exception as e:
        logger.error(f"Inference collection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
