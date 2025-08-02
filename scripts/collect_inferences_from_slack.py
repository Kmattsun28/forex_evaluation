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
    if not all([SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_BOT_USER_ID]):
        print("Error: Slack environment variables (SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_BOT_USER_ID) must be set.")
        return
        
    client = WebClient(token=SLACK_BOT_TOKEN)
    db = next(database.get_db())
    
    print("Starting to collect inferences from the last 12 hours from Slack...")
    
    try:
        # 【修正点】過去12時間分のメッセージをページネーションですべて取得する
        oldest_timestamp = time.mktime((datetime.now() - timedelta(hours=12)).timetuple())
        
        all_messages = []
        cursor = None
        
        while True:
            response = client.conversations_history(
                channel=SLACK_CHANNEL_ID,
                oldest=str(oldest_timestamp),
                cursor=cursor,
                limit=200, # 一度に取得するメッセージ数
                inclusive=True
            )
            
            messages_page = response.get('messages', [])
            all_messages.extend(messages_page)
            
            if not response.get('has_more'):
                break
                
            cursor = response.get('response_metadata', {}).get('next_cursor')
            print(f"Fetched {len(messages_page)} messages, getting next page for this time window...")
            time.sleep(1) # APIレートリミットを避ける

        # APIはデフォルトで新しい順にメッセージを返す
        print(f"Found a total of {len(all_messages)} messages in the last 12 hours.")
        
        # 新しい順に処理
        for i, msg in enumerate(all_messages):
            # 1. 「推論結果」メッセージを特定する
            if (msg.get('user') == SLACK_BOT_USER_ID and '推論結果:' in msg.get('text', '')):
                
                inference_result_message = msg
                prompt_message = None

                # 2. ペアとなる「使用プロンプト」メッセージを探す
                # スレッド内のメッセージを検索
                if 'thread_ts' in inference_result_message:
                    # スレッドの親メッセージがプロンプトであると仮定
                    if inference_result_message['thread_ts'] == inference_result_message['ts']:
                        continue # 自分自身なのでスキップ
                    
                    # スレッドの親メッセージを取得
                    thread_info_response = client.conversations_history(
                        channel=SLACK_CHANNEL_ID,
                        latest=inference_result_message['thread_ts'],
                        inclusive=True,
                        limit=1
                    )
                    parent_message = thread_info_response['messages'][0] if thread_info_response['messages'] else None

                    if parent_message and '使用プロンプト' in parent_message.get('text', '') and parent_message.get('files'):
                        prompt_message = parent_message
                else:
                    # スレッド外の場合、直後の「使用プロンプト」メッセージを探す
                    # APIは新しい順なので、インデックスが後のものが時間的には古いメッセージ
                    for j in range(i + 1, len(all_messages)):
                        next_message = all_messages[j]
                        if next_message.get('user') == SLACK_BOT_USER_ID:
                            if '使用プロンプト' in next_message.get('text', '') and next_message.get('files'):
                                prompt_message = next_message
                                break # 見つかったらループを抜ける
                            if '推論結果:' in next_message.get('text', ''):
                                # 別の推論結果に到達したら、ペアではないので探索終了
                                break
                
                if not prompt_message:
                    # print(f"Warning: Inference result found at {inference_result_message['ts']}, but no matching prompt message found.")
                    continue

                # 3. DBにすでに存在するか確認 (重複防止)
                if crud.get_inference_by_slack_ts(db, slack_ts=prompt_message['ts']):
                    continue

                # 4. プロンプトファイルの内容を取得
                prompt_text = ""
                if prompt_message.get('files'):
                    file_info = prompt_message['files'][0]
                    if file_info.get('filetype') == 'text' or file_info.get('name', '').endswith('.txt'):
                        file_content_response = requests.get(
                            file_info.get('url_private'),
                            headers={'Authorization': f'Bearer {SLACK_BOT_TOKEN}'}
                        )
                        if file_content_response.status_code == 200:
                            prompt_text = file_content_response.text

                if not prompt_text:
                    # print(f"Warning: Could not retrieve prompt text for message {prompt_message['ts']}.")
                    continue

                # 5. データベースに保存
                inference_data = TradeInferenceCreate(
                    slack_message_ts=prompt_message['ts'],
                    inference_time=datetime.fromtimestamp(float(prompt_message['ts'])),
                    prompt=prompt_text,
                    raw_response=inference_result_message.get('text', ''),
                    inferred_actions=[]
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