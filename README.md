# 為替取引評価システム v2.5

為替取引の推論ログをSlackから自動収集し、実績取引と紐付けて評価するシステムです。さらに、リアルタイム為替レートを基に現在の資産状況と評価損益を計算し、Slackへ定期的にレポートします。

## 🎯 プロジェクト概要

このシステムは、既存のDocker構成と推論・Slack通知フローを完全に維持しつつ、以下の高度な評価・レポーティング機能を提供します。

  - **Slackからの推論ログ自動収集**: 複雑なメッセージ形式（スレッド形式、連続投稿）に対応し、推論ログを自動でデータベースに記録します。
  - **実績取引との自動紐付け**: 取引履歴JSONファイルをインポートし、最も時間的に近い推論ログと自動で関連付けます。
  - **LLMによるパフォーマンス評価**: 蓄積されたデータを基に、評価用LLMが各推論のロジックやパフォーマンスを多角的に分析します。
  - **資産状況のリアルタイムレポート (新機能)**: 初期資産を元に全取引をシミュレートし、手数料を考慮した現在の保有資産、評価損益、実現損益を計算してSlackに通知します。
  - **カスタマイズ可能なアラート機能 (新機能)**: 総資産の増減や、各通貨の評価損益が設定した閾値を超えた場合に、`@channel`メンション付きで強力なアラートを送信します。
  - **自動レポート生成**: 日次・週次でのパフォーマンスサマリーを自動で生成し、Slackへ投稿します。
  - **RESTful API**: 評価結果やサマリーに外部からアクセスするためのAPIを提供します。

## 📁 プロジェクト構造

```
forex_evaluation/
├── app/                  # FastAPIアプリケーション
│   ├── main.py          # APIエンドポイント
│   ├── models.py        # データベーステーブル定義
│   ├── schemas.py       # Pydanticスキーマ
│   ├── crud.py          # データベース操作
│   ├── database.py      # DB接続設定
│   ├── scheduler.py     # 定期実行タスク管理
│   └── engine/          # ビジネスロジック
│       └── evaluation_engine.py   # 評価エンジン
├── scripts/             # バッチ処理スクリプト
│   ├── collect_inferences_from_slack.py  # Slack収集
│   ├── import_trades.py           # 取引データインポート
│   ├── run_evaluation.py          # 評価実行
│   ├── generate_report.py         # パフォーマンスレポート生成
│   └── calculate_holdings_pnl.py  # 資産状況レポート生成 (新機能)
├── tests/               # 自動テスト
├── db/                  # SQLiteデータベース
├── docker-compose.yml   # Docker構成
├── Dockerfile          # コンテナ定義
├── requirements.txt    # Python依存関係
└── .env               # 環境変数
```

## 🚀 セットアップ

### 1\. 環境変数の設定

`.env.sample`をコピーして`.env`ファイルを作成し、あなたの環境に合わせて以下の値を設定します。

```bash
# .env

# Slack API設定
SLACK_BOT_TOKEN="xoxb-your-actual-slack-bot-token"
SLACK_CHANNEL_ID="C123456789"         # 推論ログを監視するチャンネルID
SLACK_BOT_USER_ID="U123456789"        # 推論を投稿するBotのユーザーID
SLACK_REPORT_CHANNEL_ID="C123456789" # パフォーマンスレポートの送信先
SLACK_HOLDINGS_WEBHOOK_URL="https://hooks.slack.com/services/..." # 資産状況レポートの送信先Webhook URL

# アラート通知の閾値設定
# --- 長期（マイルストーン）アラート ---
TOTAL_ASSETS_PROFIT_THRESHOLD=1.10 # 総資産が初期資金の1.10倍 (10%増) を超えたら通知
TOTAL_ASSETS_LOSS_THRESHOLD=0.925  # 総資産が初期資金の0.925倍 (7.5%減) を下回ったら通知

# --- 超短期（機会検知）アラート ---
USD_PNL_ALERT_YEN=1500 # USDの評価損益(円換算)の絶対値が1500円を超えたら通知
EUR_PNL_ALERT_YEN=1500 # EURの評価損益(円換算)の絶対値が1500円を超えたら通知
```

### 2\. Pythonライブラリの確認

`requirements.txt`に以下のライブラリが含まれていることを確認してください。
`yfinance`, `beautifulsoup4`

### 3\. システムの起動

```bash
# コンテナをビルドしてバックグラウンドで起動
docker compose up --build -d

# ログを確認
docker compose logs -f
```

## 🔧 手動操作とテスト

### スクリプトの個別実行

```bash
# Slackから推論ログを収集
docker compose run --rm forex python3 scripts/collect_inferences_from_slack.py

# 取引履歴JSONをインポート
docker compose run --rm forex python3 scripts/import_trades.py

# 評価を実行
docker compose run --rm forex python3 scripts/run_evaluation.py

# 資産状況レポートをテスト生成
docker compose run --rm forex python3 scripts/calculate_holdings_pnl.py
```

### 自動テストの実行

```bash
# 全テストを実行
docker compose run --rm forex pytest
```

## 📡 API エンドポイント

APIは `http://<サーバーIP>:18000` で公開されます。

  - `GET /`: システムの基本情報
  - `GET /docs`: APIのドキュメント (Swagger UI)
  - `GET /reports/summary?period={daily|weekly|all_time}`: パフォーマンスサマリー
  - `GET /evaluations/{inference_id}`: 個別の評価結果

## 🔄 定期実行スケジュール

| タスク | 実行ファイル | 頻度 | 説明 |
| :--- | :--- | :--- | :--- |
| **Slackログ収集** | `collect_inferences_from_slack.py` | 1時間ごと | 新しい推論メッセージを収集 |
| **個別評価実行** | `run_evaluation.py` | 1時間ごと | 未評価の推論を評価 |
| **資産状況レポート** | `calculate_holdings_pnl.py` | 10分ごと | 最新の資産状況と評価損益をSlackに通知 |
| **日次レポート** | `generate_report.py --period daily` | 毎日 00:00 | 過去24時間のパフォーマンスサマリーをSlackに通知 |
| **週次レポート** | `generate_report.py --period weekly` | 毎週土曜 12:00 | 週間パフォーマンスサマリーをSlackに通知 |