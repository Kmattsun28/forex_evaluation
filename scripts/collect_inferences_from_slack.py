# scripts/collect_inferences_from_slack.py

import os
import time
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from datetime import datetime, timedelta

# 親ディレクトリをPythonパスに追加
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import crud, database
from app.schemas import TradeInferenceCreate

# 環境変数の読み込み
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
SLACK_BOT_USER_ID = os.getenv("SLACK_BOT_USER_ID")

def collect_inferences():
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Error: SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must be set in environment variables")
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    db = next(database.get_db())
    
    print("Starting to collect inferences from Slack...")
    
    try:
        # 過去24時間分のメッセージを取得
        oldest_timestamp = time.mktime((datetime.now() - timedelta(hours=24)).timetuple())
        
        response = client.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=oldest_timestamp,
            limit=200 # 必要に応じて調整
        )
        
        messages = response['messages']
        print(f"Found {len(messages)} messages in the last 24 hours.")

        # メッセージを古い順に処理するため逆順にする
        messages_reversed = list(reversed(messages))
        
        for i, msg in enumerate(messages_reversed):
            
            # 1. 「使用プロンプト」メッセージを探す
            if (msg.get('user') == SLACK_BOT_USER_ID and
                '使用プロンプト' in msg.get('text', '') and
                msg.get('files')):

                prompt_message = msg
                
                # 2. DBにすでに存在するか確認
                existing_inference = crud.get_inference_by_slack_ts(db, slack_ts=prompt_message['ts'])
                if existing_inference:
                    continue

                # 3. ペアとなる「推論結果」メッセージを探す
                inference_result_message = None
                
                # スレッド内の場合
                if 'thread_ts' in prompt_message:
                    try:
                        thread_replies = client.conversations_replies(
                            channel=SLACK_CHANNEL_ID,
                            ts=prompt_message['thread_ts']
                        )
                        for reply in thread_replies['messages']:
                            if '推論結果:' in reply.get('text', ''):
                                inference_result_message = reply
                                break
                    except SlackApiError as e:
                        print(f"Error fetching thread replies: {e}")
                        
                # スレッド外の場合 (直前のメッセージを確認)
                if not inference_result_message and i > 0:
                    prev_message = messages_reversed[i-1]
                    if '推論結果:' in prev_message.get('text', ''):
                        inference_result_message = prev_message

                if not inference_result_message:
                    print(f"Warning: Prompt message found at {prompt_message['ts']}, but no matching inference result message found.")
                    continue

                # 4. プロンプトファイルの内容を取得
                prompt_text = ""
                try:
                    file_info = prompt_message['files'][0]
                    if file_info.get('filetype') == 'text' or file_info.get('name', '').endswith('.txt'):
                        file_response = client.files_info(file=file_info['id'])
                        file_content_response = requests.get(
                            file_response['file']['url_private'],
                            headers={'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
                        )
                        if file_content_response.status_code == 200:
                            prompt_text = file_content_response.text
                except Exception as e:
                    print(f"Error retrieving file content: {e}")

                if not prompt_text:
                    print(f"Warning: Could not retrieve prompt text for message {prompt_message['ts']}. Using placeholder.")
                    prompt_text = "プロンプト取得に失敗しました"

                # 5. データベースに保存
                try:
                    inference_data = TradeInferenceCreate(
                        slack_message_ts=prompt_message['ts'],
                        inference_time=datetime.fromtimestamp(float(prompt_message['ts'])),
                        prompt=prompt_text,
                        raw_response=inference_result_message.get('text', ''),
                        inferred_actions=[]  # 後で推論エンジンで解析される
                    )
                    crud.create_trade_inference(db, inference=inference_data)
                    print(f"Success: New inference from {inference_data.inference_time} saved to DB.")
                except Exception as e:
                    print(f"Error saving inference to database: {e}")

    except SlackApiError as e:
        print(f"Error fetching messages from Slack: {e.response['error']}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    collect_inferences()
