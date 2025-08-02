# Dockerfile
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# システムの更新とPythonのインストール
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# データベースディレクトリを作成
RUN mkdir -p /app/db

# ポートを公開
EXPOSE 8000

# アプリケーションを起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
