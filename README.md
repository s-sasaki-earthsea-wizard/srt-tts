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
- gTTSによる事前見積もり（ElevenLabsのクレジット節約）
- LLMによるテキスト短縮（時間枠内に収めるための再意訳）
- 多言語対応（gTTSモード）
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

### SRTファイルを音声化（ElevenLabs）

```bash
make run SRT=srt/example.srt
```

出力：

- `output/example.mp3` - 音声ファイル
- `output/example.json` - オーディオタグ付きテキスト

### gTTSのみで音声化（ElevenLabs不使用）

ElevenLabsのクレジットを消費せずに音声を生成できます：

```bash
make run SRT=srt/example.srt ARGS='--gtts-only'
```

### 多言語音声の作成

gTTSモードでは`--lang`オプションで言語を指定できます。
ElevenLabsモードでは言語は自動認識されます。

#### 英語（English）

```bash
make run SRT=srt/english.srt ARGS='--gtts-only --lang en'
```

#### 中国語（繁体中文）

```bash
make run SRT=srt/chinese.srt ARGS='--gtts-only --lang zh-TW'
```

#### ロシア語（Русский）

```bash
make run SRT=srt/russian.srt ARGS='--gtts-only --lang ru'
```

#### スペイン語（Español）

```bash
make run SRT=srt/spanish.srt ARGS='--gtts-only --lang es'
```

#### 韓国語（한국어）

```bash
make run SRT=srt/korean.srt ARGS='--gtts-only --lang ko'
```

### オーディオタグ付きJSONのみ出力（TTS無し）

開発・デバッグ用にTTSをスキップしてJSONのみを出力：

```bash
make run SRT=srt/example.srt JSON_ONLY=1
```

### その他のオプション

```bash
# 速度調整の閾値を変更（デフォルト: 1.0）
make run SRT=srt/example.srt ARGS='--speed-threshold 0.8'

# gTTS事前見積もりの補正係数を変更（デフォルト: 0.9）
make run SRT=srt/example.srt ARGS='--estimation-ratio 0.85'

# リトライ回数を変更
make run SRT=srt/example.srt ARGS='--gtts-shorten-retries 10 --el-shorten-retries 3'

# エントリー間のマージンを変更（デフォルト: 100ms）
make run SRT=srt/example.srt ARGS='--margin-ms 200'

# デバッグモード（LLMコンテキストと応答を詳細出力）
make run SRT=srt/example.srt ARGS='--debug'
```

### ヘルプ

```bash
make help    # ヘルプを表示
make clean   # Dockerイメージを削除
```

## オプション一覧

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--gtts-only` | - | gTTSのみで音声生成（ElevenLabsを使用しない） |
| `--lang` | ja | gTTSの言語コード（例: en, ja, ko, zh-CN, ru, es） |
| `--estimation-ratio` | 0.9 | gTTS事前見積もりの補正係数（0以下で無効化） |
| `--gtts-shorten-retries` | 8 | gTTS事前見積もりでの再意訳リトライ回数 |
| `--el-shorten-retries` | 2 | ElevenLabs生成後の再意訳リトライ回数 |
| `--speed-threshold` | 1.0 | 速度調整の閾値（これ以下で再意訳を試行） |
| `--margin-ms` | 100 | エントリー間の最低マージン（ミリ秒） |
| `--no-tags` | - | オーディオタグの付与をスキップ |
| `--json-only` | - | TTSをスキップしてJSONのみ出力 |
| `--debug` | - | デバッグモードを有効化 |

## 処理フロー

```
SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] オーディオタグ付与（前後2エントリーのコンテキスト参照）
    ↓
[gTTS] 事前見積もり → 時間超過なら最大8回まで短縮を試行
    ↓
[ElevenLabs TTS] 音声合成
    ↓
[速度調整] 時間超過なら最大2回まで短縮を試行 → それでも超過なら速度調整
    ↓
[音声結合] 最終MP3ファイル生成
```

## プロジェクト構成

```
srt-tts/
├── src/
│   ├── app.py              # メインアプリケーション
│   ├── parsers/            # SRTパーサー
│   ├── clients/            # API クライアント（TTS, LLM, gTTS）
│   ├── audio/              # 音声処理
│   └── processors/         # オーディオタグ処理
├── srt/                    # 入力SRTファイル
├── output/                 # 出力ファイル
├── Dockerfile
├── docker-compose.yml
└── Makefile
```
