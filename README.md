# SRT-TTS

SRTファイルをElevenLabs APIで音声化するツール

## 概要

SRT字幕ファイルを読み込み、タイムスタンプに基づいて音声ファイルを生成します。
LLMを使用してオーディオタグ（表現タグ）を自動付与し、より自然で表現豊かな音声を生成できます。

### 主な機能

- SRTファイルのパースとタイムスタンプ抽出
- ElevenLabs TTS APIによる音声合成
- LLMによるオーディオタグの自動付与（ElevenLabs v3対応）
- 音声長がタイムスタンプを超える場合の速度調整
- タグ付きテキストのJSON出力

## 開発環境

- Docker / Docker Compose
- Python 3.11+

## セットアップ

1. リポジトリをクローン

2. 環境変数を設定

```bash
cp env.example .env
```

`.env`ファイルを編集して以下のAPIキーを設定：

- `ELEVENLABS_API_KEY`: ElevenLabs APIキー
- `ELEVENLABS_VOICE_ID`: 使用する音声ID
- `LLM_API_KEY`: LLM APIキー（オーディオタグ用）
- `LLM_BASE_URL`: LLM APIのベースURL
- `LLM_MODEL`: 使用するLLMモデル

3. Dockerイメージをビルド

```bash
make build
```

## 使い方

### SRTファイルを音声化

```bash
make run SRT=srt/example.srt
```

出力：

- `output/example.mp3` - 音声ファイル
- `output/example.json` - オーディオタグ付きテキスト

### オーディオタグ付きJSONのみ出力（TTS無し）

開発・デバッグ用にTTSをスキップしてJSONのみを出力：

```bash
make run SRT=srt/example.srt JSON_ONLY=1
```

### その他のコマンド

```bash
make help    # ヘルプを表示
make clean   # Dockerイメージを削除
```

## プロジェクト構成

```
srt-tts/
├── src/
│   ├── app.py              # メインアプリケーション
│   ├── parsers/            # SRTパーサー
│   ├── clients/            # API クライアント（TTS, LLM）
│   ├── audio/              # 音声処理
│   └── processors/         # オーディオタグ処理
├── srt/                    # 入力SRTファイル
├── output/                 # 出力ファイル
├── Dockerfile
├── docker-compose.yml
└── Makefile
```
