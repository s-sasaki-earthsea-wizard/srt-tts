# SRT-TTS

SRTファイルを音声化するツール。既定はローカルで動くVoxCPM2（MLX 4bit版、Apple Silicon）で、ElevenLabs APIとgTTSも選べます。

## 概要

SRT字幕ファイルを読み込み、タイムスタンプに基づいて音声ファイルを生成します。
時間枠に収まらない字幕はLLMで短縮し、それでも収まらなければ速度調整します。

### 主な機能

- SRTファイルのパースとタイムスタンプ抽出
- **VoxCPM2によるローカル音声合成（既定）**
  - MLX版の4bit量子化モデル（`mlx-community/VoxCPM2-4bit`）をApple SiliconのGPU（Metal）で実行
  - `voices/<lang>/` の参照音声と書き起こしから声を複製し、エントリー間で声を揃える
- ElevenLabs TTS APIによる音声合成（オプション、有料）
- LLMによるオーディオタグの自動付与（ElevenLabs v3向け、`--tags` で有効化）
- 音声長がタイムスタンプを超える場合の速度調整
- gTTSによる事前見積もり（音声合成の回数を節約）
- LLMによるテキスト短縮（時間枠内に収めるための再意訳）
- 短縮テキストの意味一貫性チェック（LLMによる意味ズレ検出）
- 多言語対応（`--lang` で指定）
- タグ付きテキストのJSON出力
- 言語バリデーション（出力が指定言語と異なる場合の自動再生成）
- **吹き替え脚本生成**（日本語SRT → 他言語SRT + 音声）
  - gTTSで発話時間を見積もり、タイムスタンプを自動調整
  - 時間枠に収まらない場合はLLMで再翻訳（整合性確認付き）

## 開発環境

- macOS（Apple Silicon）: VoxCPM2はMLXで動くため必須。ElevenLabsとgTTSの経路はLinuxでも動作
- [uv](https://docs.astral.sh/uv/)（Python 3.12の仮想環境と依存を管理）
- ffmpeg（pydubとffprobeが使用）

## セットアップ

1. リポジトリをクローン

2. ツールと依存パッケージをインストール

```bash
brew install uv ffmpeg
make setup        # uv sync
```

3. 環境変数を設定

```bash
cp env.example .env
```

`.env`ファイルを編集して以下を設定：

- `LLM_API_KEY`: LLM APIキー（短縮・意味一貫性チェック・オーディオタグ用）
- `LLM_BASE_URL`: LLM APIのベースURL
- `LLM_MODEL`: 使用するLLMモデル
- `TTS_API_KEY` / `TTS_VOICE_ID` / `TTS_MODEL`: ElevenLabsを使う場合のみ（オーディオタグは `eleven_v3` で有効）
- `VOXCPM_MODEL` / `VOXCPM_VOICE_DIR`: VoxCPMのモデルと参照音声ディレクトリを変える場合のみ

4. 参照音声を配置（VoxCPM）

```text
voices/
├── en/
│   ├── reference.mp3   # 参照音声（.wav / .mp3 / .flac）
│   └── reference.txt   # 参照音声の正確な書き起こし
├── ko/
└── zh/
```

- `reference.txt` があれば書き起こし付きの複製（最も忠実）、なければ音声のみの複製になる
- `zh-CN` や `pt-BR` は `voices/zh`、`voices/pt` にフォールバックする
- 参照音声がない言語はゼロショット合成になり、エントリーごとに声が変わりうる
- 参照音声は `.gitignore` で除外され、ディレクトリ構造（`.gitkeep`）だけがgitに入る
- 参照音声には、本人の同意を得た声か、権利上問題のない合成音声を使う

初回実行時にモデル（約2.3 GB）がHugging Faceのキャッシュにダウンロードされます。

## 使い方

### SRTファイルを音声化（VoxCPM2、既定）

```bash
make run SRT=srt/example-en.srt LANG=en
```

出力：

- `output/example-en.mp3` - 音声ファイル
- `output/example-en.json` - 処理後のテキスト（短縮結果など）
- `output/example-en.tagged.srt` - 処理後のテキストを反映したSRT
- `output/example-en.warnings.json` - 時間超過や整合性チェック不合格があった場合のみ

`LANG` は必須です。gTTSの言語、VoxCPMの参照音声の選択、LLM出力の言語バリデーションに使われます。

### ElevenLabsで音声化（オプション、有料）

```bash
make run SRT=srt/example-en.srt LANG=en ARGS='--tts-provider elevenlabs --tags'
```

`--tags` はLLMでElevenLabs v3用のオーディオタグを付与します。VoxCPMやgTTSではタグを読み上げないよう除去するため、付与しても効果はありません。

### gTTSのみで音声化

```bash
make run SRT=srt/example-en.srt LANG=en ARGS='--gtts-only'
```

### 多言語音声の作成

```bash
make run SRT=srt/example-en.srt LANG=en      # 英語
make run SRT=srt/example-ko.srt LANG=ko      # 韓国語
make run SRT=srt/example-zh.srt LANG=zh-CN   # 中国語（簡体字）
make run SRT=srt/example-zh.srt LANG=zh-TW   # 中国語（繁体字）
make run SRT=srt/example-pt.srt LANG=pt-BR   # ポルトガル語（ブラジル）
```

VoxCPM2は30言語に対応しています（[モデルカード](https://huggingface.co/openbmb/VoxCPM2)）。
参照音声のない言語は、その言語の `voices/<lang>/` を用意するまで声が揃いません。

### テキストのJSONのみ出力（TTS無し）

開発・デバッグ用にTTSをスキップしてJSONのみを出力：

```bash
make run SRT=srt/example-en.srt LANG=en JSON_ONLY=1
```

## 吹き替え脚本生成

日本語SRTファイルから他言語の吹き替え用SRTと音声を生成します。

### 吹き替えSRTのみ生成

```bash
make dub SRT=srt/video-jp.srt LANG=en
```

出力：`srt/video-en.srt`

### 吹き替えSRT + 音声を生成

```bash
make dub-audio SRT=srt/video-jp.srt LANG=en
```

出力：`srt/video-en.srt` + `srt/video-en.mp3`

### 既存SRTから音声のみ生成

SRTを手動で編集した後に音声を再生成する場合：

```bash
make synth SRT=srt/video-en.srt LANG=en
```

出力：`srt/video-en.mp3`

### 対応言語の例

```bash
make dub-audio SRT=srt/video-jp.srt LANG=en    # 英語
make dub-audio SRT=srt/video-jp.srt LANG=ru    # ロシア語
make dub-audio SRT=srt/video-jp.srt LANG=es    # スペイン語
make dub-audio SRT=srt/video-jp.srt LANG=ko    # 韓国語
make dub-audio SRT=srt/video-jp.srt LANG=zh-CN # 中国語（簡体字）
```

### 吹き替え生成の処理フロー

```text
日本語SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] ターゲット言語へ翻訳
    ↓
[gTTS] 発話時間見積もり
    ↓
[タイムスタンプ調整]
  - 時間枠内に収まる → そのまま
  - 超過 → 前の隙間を使う / 次の字幕まで使う
  - それでも超過 → LLMで再翻訳（整合性確認付き）
    ↓
[音声合成（オプション）] gTTSで音声生成 + 必要に応じて速度調整
    ↓
翻訳済みSRT（+ MP3）ファイル生成
```

### その他のオプション

```bash
# 速度調整の閾値を変更（デフォルト: 1.0）
make run SRT=srt/example-en.srt LANG=en ARGS='--speed-threshold 0.8'

# gTTS事前見積もりの補正係数を変更（デフォルト: 1.0）
make run SRT=srt/example-en.srt LANG=en ARGS='--estimation-ratio 0.9'

# 文字数削減の目標係数を変更（デフォルト: 0.95）
make run SRT=srt/example-en.srt LANG=en ARGS='--shorten-ratio 0.9'

# リトライ回数を変更
make run SRT=srt/example-en.srt LANG=en ARGS='--gtts-shorten-retries 8 --tts-shorten-retries 3'

# エントリー間のマージンを変更（デフォルト: 100ms）
make run SRT=srt/example-en.srt LANG=en ARGS='--margin-ms 200'

# デバッグモード（LLMコンテキストと応答を詳細出力）
make run SRT=srt/example-en.srt LANG=en ARGS='--debug'
```

### ヘルプ

```bash
make help    # ヘルプを表示
```

## オプション一覧

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--tts-provider` | voxcpm | 音声合成エンジン（`voxcpm`: ローカル、`elevenlabs`: 有料API） |
| `--tags` | - | LLMでElevenLabs用オーディオタグを付与（既定は無効） |
| `--gtts-only` | - | gTTSのみで音声生成（VoxCPM/ElevenLabsを使用しない） |
| `--lang` | ja | 言語コード（例: en, ja, ko, zh-CN, zh-TW, ru, es, id, pt-BR, hi）。Makeでは `LANG=` で指定 |
| `--estimation-ratio` | 1.0 | gTTS事前見積もりの補正係数（0以下で無効化） |
| `--gtts-shorten-retries` | 6 | gTTS事前見積もりでの再意訳リトライ回数 |
| `--tts-shorten-retries` | 6 | 音声合成後の再意訳リトライ回数 |
| `--speed-threshold` | 1.0 | 速度調整の閾値（これ以下で再意訳を試行） |
| `--shorten-ratio` | 0.95 | 文字数削減の目標係数 |
| `--margin-ms` | 100 | エントリー間の最低マージン（ミリ秒） |
| `--no-consistency-check` | - | 短縮テキストの意味一貫性チェックを無効化 |
| `--json-only` | - | TTSをスキップしてJSONのみ出力 |
| `--debug` | - | デバッグモードを有効化 |

## 処理フロー

```
SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] オーディオタグ付与（--tags 指定時のみ、前後2エントリーのコンテキスト参照）
    ↓
[gTTS] 事前見積もり → 時間超過ならLLMで最大6回まで短縮を試行（言語バリデーション・意味一貫性チェック付き）
    ↓
[TTS] VoxCPM2（既定、ローカル）または ElevenLabs で音声合成
    ↓
[速度調整] 時間超過なら最大6回まで短縮を試行（意味一貫性チェック付き） → それでも超過なら速度調整
    ↓
[音声結合] 最終MP3ファイル生成
```

## プロジェクト構成

```text
srt-tts/
├── src/
│   ├── app.py              # 音声化メインアプリケーション
│   ├── dub.py              # 吹き替え脚本生成
│   ├── synth.py            # 既存SRTから音声合成
│   ├── parsers/            # SRTパーサー
│   ├── clients/            # TTS（VoxCPM, ElevenLabs）・LLM・gTTS クライアント
│   ├── audio/              # 音声処理
│   ├── processors/         # オーディオタグ・吹き替え脚本処理
│   ├── prompts/            # LLMプロンプト
│   └── validators/         # 言語・意味一貫性バリデーション
├── srt/                    # 入力SRTファイル
├── voices/                 # VoxCPMの参照音声（言語ごと、gitには構造のみ）
├── output/                 # 出力ファイル
├── pyproject.toml          # 依存パッケージ（uv）
├── uv.lock
└── Makefile
```

## クレジット

| 対象 | 提供元 | ライセンス |
| --- | --- | --- |
| [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2)（モデル） | OpenBMB | Apache-2.0 |
| [VoxCPM2-4bit](https://huggingface.co/mlx-community/VoxCPM2-4bit)（MLX量子化版、本ツールの既定モデル） | mlx-community | Apache-2.0 |
| [mlx-audio](https://github.com/Blaizzy/mlx-audio)（推論ライブラリ） | Prince Canuma | MIT |

VoxCPMの提供元は、生成音声をAIによるものと明示するよう強く推奨しています（[Risks and Limitations](https://github.com/OpenBMB/VoxCPM/blob/300e4260b509066151d623dc9c0aa922cf82232b/README.md#%EF%B8%8F-risks-and-limitations)）：

> It is **strictly forbidden** to use VoxCPM for impersonation, fraud, or disinformation. We strongly recommend clearly marking any AI-generated content.
