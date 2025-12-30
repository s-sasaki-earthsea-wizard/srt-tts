FROM python:3.11-slim

# ffmpegをインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY src/ ./src/

# 入出力ディレクトリを作成
RUN mkdir -p /app/srt /app/output

CMD ["python", "-m", "src.app"]
