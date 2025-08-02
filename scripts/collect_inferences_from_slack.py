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
    if not all([SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_BOT_USER_ID]):
        print("Error: Slack environment variables (SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_BOT_USER_ID) must be set.")
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    db = next(database.get_db())
    
    print("Starting to collect inferences from Slack...")
    
    try:
        # 過去24時間分のメッセージを取得
        oldest_timestamp = time.mktime((datetime.now() - timedelta(hours=24)).timetuple())
        
        response = client.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=str(oldest_timestamp),
            limit=500 # 24時間以内のメッセージを十分にカバーできる数を指定
        )
        
        messages = response['messages']
        print(f"Found {len(messages)} messages in the last 24 hours.")

        # メッセージを時系列（古い順）にソート
        messages.sort(key=lambda x: float(x.get('ts', 0)))
        
        for i, msg in enumerate(messages):
            # 1. 「使用プロンプト」メッセージを特定する
            if (msg.get('user') == SLACK_BOT_USER_ID and
                '使用プロンプト' in msg.get('text', '') and
                msg.get('files')):

                prompt_message = msg
                
                # 2. DBにすでに存在するか確認 (重複防止)
                if crud.get_inference_by_slack_ts(db, slack_ts=prompt_message['ts']):
                    continue

                # 3. ペアとなる「推論結果」メッセージを探す
                inference_result_message = None
                
                # スレッド内のメッセージを検索
                if 'thread_ts' in prompt_message:
                    thread_replies_response = client.conversations_replies(
                        channel=SLACK_CHANNEL_ID,
                        ts=prompt_message['thread_ts']
                    )
                    for reply in thread_replies_response['messages']:
                        if '推論結果:' in reply.get('text', '') and reply.get('user') == SLACK_BOT_USER_ID:
                            inference_result_message = reply
                            break
                # スレッド外の場合、直前のBotメッセージを検索
                else:
                    # 自分より前のメッセージを逆順に探索
                    for j in range(i - 1, -1, -1):
                        prev_message = messages[j]
                        # 自分と同じBotからのメッセージか確認
                        if prev_message.get('user') == SLACK_BOT_USER_ID:
                            if '推論結果:' in prev_message.get('text', ''):
                                inference_result_message = prev_message
                                break # 見つかったらループを抜ける
                            # 別のプロンプトメッセージに到達したら、ペアではないので探索終了
                            if '使用プロンプト' in prev_message.get('text', ''):
                                break
                
                if not inference_result_message:
                    print(f"Warning: Prompt message found at {prompt_message['ts']}, but no matching inference result message found.")
                    continue

                # 4. プロンプトファイルの内容を取得
                prompt_text = ""
                file_info = prompt_message['files'][0]
                if file_info.get('filetype') == 'text' or file_info.get('name', '').endswith('.txt'):
                    file_content_response = requests.get(
                        file_info.get('url_private'),
                        headers={'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
                    )
                    if file_content_response.status_code == 200:
                        prompt_text = file_content_response.text

                if not prompt_text:
                    print(f"Warning: Could not retrieve prompt text for message {prompt_message['ts']}.")
                    continue

                # 5. データベースに保存
                inference_data = TradeInferenceCreate(
                    slack_message_ts=prompt_message['ts'],
                    inference_time=datetime.fromtimestamp(float(prompt_message['ts'])),
                    prompt=prompt_text,
                    raw_response=inference_result_message.get('text', ''),
                    inferred_actions=[] # この時点では空。評価エンジンで解析・入力する想定。
                )
                crud.create_trade_inference(db, inference=inference_data)
                print(f"Success: New inference from {inference_data.inference_time} saved to DB.")

    except SlackApiError as e:
        print(f"Error fetching messages from Slack: {e.response['error']}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    collect_inferences()

