# 為替取引評価システム v2.3

完全に独立したデータ収集プロセスとしてSlackから過去の推論ログを取得し、収集したデータを基に評価パイプラインを実行する、再現性と拡張性の高いクリーンなシステムです。

## 🎯 プロジェクト概要

このシステムは既存のDocker構成と推論・Slack通知フローを完全に維持し、以下の機能を提供します：

- **Slackからの推論ログ自動収集** - 10分ごとの定期収集
- **AI推論の品質評価** - ロジック分析とパフォーマンス予測
- **実績取引との自動紐付け** - JSONファイルからのインポート
- **自動レポート生成** - 日次・週次・月次レポート
- **RESTful API** - 全データへのプログラマティックアクセス

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
│       ├── inference_engine.py    # 推論解析エンジン
│       └── evaluation_engine.py   # 評価エンジン
├── scripts/             # バッチ処理スクリプト
│   ├── collect_inferences_from_slack.py  # Slack収集
│   ├── import_trades.py           # 取引データインポート
│   ├── run_evaluation.py          # 評価実行
│   └── generate_report.py         # レポート生成
├── tests/               # 自動テスト
├── db/                  # SQLiteデータベース
├── docker-compose.yml   # Docker構成
├── Dockerfile          # コンテナ定義
├── requirements.txt    # Python依存関係
└── .env               # 環境変数
```

## 🚀 セットアップ

### 1. 環境変数の設定

`.env`ファイルを編集してSlack認証情報を設定：

```bash
# Slack API設定
SLACK_BOT_TOKEN="xoxb-your-actual-slack-bot-token"
SLACK_CHANNEL_ID="C123456789"  # 監視対象チャンネルID
SLACK_REPORT_CHANNEL_ID="C123456789"  # レポート送信先チャンネルID
```

### 2. システムの起動

```bash
# コンテナをビルドしてバックグラウンドで起動
docker compose up --build -d

# ログを確認
docker compose logs -f forex
```

### 3. 取引データのインポート

```bash
# 取引履歴JSONをインポート
docker compose run --rm forex python scripts/import_trades.py
```

## 📊 主要機能

### 自動データ収集
- **Slack推論ログ収集**: 10分ごとに新しい推論メッセージを自動収集
- **取引データインポート**: JSON形式の取引履歴を自動で推論と紐付け

### AI評価エンジン
- **ロジック妥当性評価**: 市場分析・テクニカル指標・リスク管理の観点から1-5点で評価
- **ポテンシャル損益計算**: 推論の潜在的な収益性を定量化
- **改善提案生成**: パフォーマンス向上のための具体的な提案

### 自動レポート
- **日次レポート**: 毎日AM 7:00に過去24時間の成果をSlack通知
- **週次レポート**: 毎週月曜AM 7:30に週間パフォーマンスを配信
- **月次レポート**: 毎月1日AM 8:00に月間総括レポートを送信

## 🔧 手動操作

### スクリプトの個別実行

```bash
# Slackから推論を収集
docker compose run --rm forex python scripts/collect_inferences_from_slack.py

# 評価を実行
docker compose run --rm forex python scripts/run_evaluation.py --max-evaluations 100

# レポートを生成
docker compose run --rm forex python scripts/generate_report.py --period daily
```

### テストの実行

```bash
# 全テストを実行
docker compose run --rm forex pytest

# 特定のテストファイルを実行
docker compose run --rm forex pytest tests/test_main_api.py -v
```

## 📡 API エンドポイント

### 基本情報
- `GET /` - システム情報
- `GET /health` - ヘルスチェック
- `GET /scheduler/status` - スケジューラー状態

### 推論管理
- `POST /inferences/` - 新しい推論を作成
- `GET /inferences/` - 推論一覧を取得
- `GET /inferences/{id}` - 特定の推論を取得

### 取引管理
- `POST /trades/` - 新しい取引を作成
- `GET /trades/inference/{id}` - 推論に関連する取引を取得

### 評価管理
- `POST /evaluations/` - 新しい評価を作成
- `GET /evaluations/{inference_id}` - 推論の評価結果を取得

### レポート
- `GET /reports/summary?period={daily|weekly|monthly|all_time}` - パフォーマンスサマリー
- `GET /reports/evaluations?period={daily|weekly|monthly|all_time}` - 評価詳細

## 🗄️ データベース設計

### 主要テーブル

1. **`trade_inferences`** - 推論ログ
   - Slackメッセージ、プロンプト、レスポンス、構造化アクション

2. **`actual_trades`** - 実績取引
   - 取引時刻、通貨ペア、アクション、価格、損益

3. **`trade_evaluations`** - 評価結果
   - ロジックスコア、潜在損益、評価コメント、改善提案

4. **`technical_indicators`** - テクニカル指標（既存）
5. **`news_articles`** - ニュース記事（既存）

## 📈 パフォーマンス指標

システムは以下の指標を自動計算・レポートします：

- **勝率**: 利益取引の割合
- **総損益**: 全取引の累積収益
- **プロフィットファクター**: 総利益 ÷ 総損失
- **平均利益・損失**: 勝ち取引・負け取引の平均値
- **推論品質スコア**: AI評価による1-5点のロジック評価
- **評価完了率**: 推論に対する評価実施率

## 🔄 定期実行スケジュール

| タスク | 頻度 | 説明 |
|--------|------|------|
| Slack収集 | 10分ごと | 新しい推論メッセージを収集 |
| 評価実行 | 1時間ごと | 未評価の推論を評価 |
| 日次レポート | 毎日 7:00 | 過去24時間のサマリー |
| 週次レポート | 月曜 7:30 | 過去7日間の分析 |
| 月次レポート | 1日 8:00 | 月間パフォーマンス総括 |

## 🛠️ トラブルシューティング

### よくある問題

1. **Slack認証エラー**
   ```bash
   # トークンが正しく設定されているか確認
   docker compose run --rm forex python -c "import os; print(os.getenv('SLACK_BOT_TOKEN'))"
   ```

2. **データベース接続エラー**
   ```bash
   # DBディレクトリの権限を確認
   ls -la db/
   ```

3. **評価が実行されない**
   ```bash
   # スケジューラーの状態を確認
   curl http://localhost:18000/scheduler/status
   ```

### ログの確認

```bash
# アプリケーションログ
docker compose logs forex

# 特定のスクリプトのログ
docker compose run --rm forex python scripts/collect_inferences_from_slack.py
```

## 🤝 開発・拡張

システムは高い拡張性を持つよう設計されています：

- **新しい評価指標**: `evaluation_engine.py`に追加
- **カスタムレポート**: `generate_report.py`を拡張
- **追加データソース**: 新しいスクリプトを`scripts/`に追加
- **API機能拡張**: `main.py`にエンドポイントを追加

## 📝 ライセンス

このプロジェクトは教育・研究目的で開発されています。

---

## システム管理

### 停止とクリーンアップ

```bash
# システムを停止
docker compose down

# 全データを削除（注意！）
docker compose down -v
rm -rf db/*
```

### バックアップ

```bash
# データベースをバックアップ
cp db/forex.sqlite db/forex_backup_$(date +%Y%m%d).sqlite
```
# forex_evaluation
