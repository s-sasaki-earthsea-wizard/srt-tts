# SRT-TTS

## プロジェクト概要

SRTファイルを音声化するツール。既定はローカルのVoxCPM2（MLX 4bit版、Apple Silicon）で、ElevenLabs APIとgTTSも選べる。時間枠に収まらない字幕はLLMで短縮する。ElevenLabs向けにはLLMでオーディオタグも付与できる。

### 技術スタック

- Python 3.12（3.11以上3.13未満。pydubが3.13で削除されたaudioopに依存）
- uv（`pyproject.toml` / `uv.lock`、ホストで実行。Dockerは廃止）
- VoxCPM2（`mlx-community/VoxCPM2-4bit`、mlx-audio 0.6.7、Apple SiliconのMetalで推論）
- ElevenLabs TTS API (v3、オプション)
- OpenAI互換 LLM API
- gTTS（Google Text-to-Speech）
- pydub（音声処理）
- pysrt（SRTパース）
- lingua-language-detector（言語検出・バリデーション）

### アーキテクチャ

#### 音声化パイプライン（src/app.py）

```text
SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] オーディオタグ付与（--tags 指定時のみ、前後2エントリーのコンテキスト参照）
    ↓
[gTTS] 事前見積もり → 時間超過ならLLMで短縮を試行（言語バリデーション・意味一貫性チェック付き）
    ↓
[TTS] VoxCPM2（既定、voices/<lang>/ の参照音声で声を複製）または ElevenLabs で音声合成
    ↓
[音声処理] 時間超過なら短縮を再試行（意味一貫性チェック付き） → それでも超過なら速度調整
    ↓
[音声結合] 最終MP3ファイル生成
```

#### 吹き替え脚本生成パイプライン（src/dub.py）

```text
日本語SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] ターゲット言語へ翻訳
    ↓
[gTTS] 発話時間見積もり
    ↓
[タイムスタンプ調整] 4段階の調整ロジック
  1. 元の時間枠内に収まる → そのまま
  2. 前の隙間を使う → 前にずらす
  3. 次の字幕が収まるなら → 次の開始まで使う
  4. 再翻訳 → LLMで短縮 + 整合性確認
    ↓
[音声合成（オプション）] gTTSで音声生成 + 速度調整
    ↓
翻訳済みSRT（+ MP3）ファイル生成
```

## 言語設定

このプロジェクトでは**日本語**での応答を行ってください。

コード内のコメント、ログメッセージ、エラーメッセージ、ドキュメンテーション文字列、コミットメッセージなどは**英文**で記述してください。

## 開発ルール

### コーディング規約

- Python: PEP 8準拠
- 関数名: snake_case
- クラス名: PascalCase
- 定数: UPPER_SNAKE_CASE
- Docstring: Google Style

## Git運用

- ブランチ戦略: feature/*, fix/*, refactor/*
- コミットメッセージ: 英文を使用、動詞から始める
- PRはmainブランチへ

## 開発ガイドライン

### ドキュメント更新プロセス

機能追加やPhase完了時には、以下のドキュメントを同期更新する：

1. **CLAUDE.md**: プロジェクト全体状況、Phase完了記録、技術仕様
2. **README.md**: ユーザー向け機能概要、実装状況、使用方法
3. **Makefile**: コマンドヘルプテキスト（## コメント）の更新

### コミットメッセージ規約

#### コミット粒度

- **1コミット = 1つの主要な変更**: 複数の独立した機能や修正を1つのコミットにまとめない
- **論理的な単位でコミット**: 関連する変更は1つのコミットにまとめる
- **段階的コミット**: 大きな変更は段階的に分割してコミット

#### プレフィックスと絵文字

- ✨ feat: 新機能
- 🐞 fix: バグ修正
- 📚 docs: ドキュメント
- 🎨 style: コードスタイル修正
- 🛠️ refactor: リファクタリング
- ⚡ perf: パフォーマンス改善
- ✅ test: テスト追加・修正
- 🏗️ chore: ビルド・補助ツール
- 🚀 deploy: デプロイ
- 🔒 security: セキュリティ修正
- 📝 update: 更新・改善
- 🗑️ remove: 削除

**重要**: AI の支援を受けた成果物には、**AI の支援を受けたことだけ**を明記する。製品名やモデル名は書かない（すぐ変わるため）。

- コミットメッセージの末尾に、次の trailer を入れる

  ```text
  Assisted-by: AI
  ```

- PR 本文の末尾に、次の1行を入れる

  ```text
  This PR was developed with AI assistance.
  ```

## 実装状況

### 完了した機能

- [x] SRTパーサー（pysrt使用）
- [x] ElevenLabs TTSクライアント
- [x] 音声速度調整（pydub使用）
- [x] 音声結合処理
- [x] LLMクライアント（OpenAI互換）
- [x] オーディオタグ自動付与
- [x] コンテキストウィンドウ（前後2エントリー参照）
- [x] タグ付きテキストのJSON出力
- [x] JSON-onlyモード（開発用）
- [x] gTTSによる事前見積もり（ElevenLabsクレジット節約）
- [x] gTTS-onlyモード（ElevenLabs不使用での音声生成）
- [x] 多言語対応（--lang オプション）
- [x] LLMによるテキスト短縮（時間枠内に収めるための再意訳）
- [x] 分離されたリトライ上限（gTTS: 4回、ElevenLabs: 2回）
- [x] 柔軟な音声配置（マージンベースの前後調整）
- [x] 言語バリデーション（lingua-pyによる出力言語チェックと再生成）
- [x] 短縮テキストの意味一貫性チェック（LLMによる意味ズレ検出）
- [x] 吹き替え脚本生成（日本語SRT → 他言語SRT）
- [x] gTTSによる発話時間見積もりとタイムスタンプ調整
- [x] 再翻訳機能（時間枠に収まらない場合のLLMによる短縮）
- [x] 再翻訳時の整合性確認（LLMによる意味保持チェック）
- [x] 既存SRTからの音声合成（synth機能）
- [x] uvによるホスト環境への移行（Docker廃止）
- [x] VoxCPM2（MLX 4bit）によるローカル音声合成を既定に（ElevenLabsはオプション）
- [x] 参照音声による声の複製（`voices/<lang>/`、書き起こしがあれば書き起こし付きで複製）
- [x] オーディオタグを既定で無効化（--tags で有効化）、LLM短縮をタグ付与から分離

## Makeターゲット

| ターゲット | 説明 |
| --- | --- |
| `setup` | uvで依存パッケージをインストール（`uv sync`） |
| `run` | SRTファイルを音声化（VoxCPM2/ElevenLabs/gTTS） |
| `run-dir` | ディレクトリ内の全SRTファイルを音声化 |
| `dub` | 日本語SRTから吹き替え用SRTを生成 |
| `dub-audio` | 日本語SRTから吹き替え用SRT+音声を生成 |
| `synth` | 既存SRTからgTTSで音声を生成 |

## CLIオプション

### 音声化（src/app.py）

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--tts-provider` | voxcpm | 音声合成エンジン（voxcpm / elevenlabs） |
| `--tags` | - | LLMでElevenLabs用オーディオタグを付与（既定は無効） |
| `--gtts-only` | - | gTTSのみで音声生成 |
| `--lang` | ja | 言語コード（gTTS・VoxCPM参照音声・言語バリデーション） |
| `--estimation-ratio` | 1.0 | gTTS事前見積もりの補正係数 |
| `--gtts-shorten-retries` | 6 | gTTS事前見積もりでの再意訳リトライ回数 |
| `--tts-shorten-retries` | 6 | 音声合成後の再意訳リトライ回数 |
| `--speed-threshold` | 1.0 | 速度調整の閾値 |
| `--shorten-ratio` | 0.95 | 文字数削減の目標係数 |
| `--margin-ms` | 100 | エントリー間の最低マージン（ミリ秒） |
| `--no-consistency-check` | - | 短縮テキストの意味一貫性チェックを無効化 |
| `--json-only` | - | TTSをスキップしてJSONのみ出力 |
| `--debug` | - | デバッグモードを有効化 |

### 吹き替え脚本生成（src/dub.py）

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--lang` | (必須) | ターゲット言語コード |
| `--margin-ms` | 100 | エントリー間の最低マージン（ミリ秒） |
| `--estimation-ratio` | 1.0 | gTTS見積もりの補正係数 |
| `--retranslation-retries` | 2 | 再翻訳のリトライ回数 |
| `--gtts-only` | - | gTTSで音声ファイルも生成 |
| `--speed-threshold` | 1.0 | 速度調整の閾値 |
| `--debug` | - | デバッグモードを有効化 |

### 音声合成（src/synth.py）

| オプション | デフォルト | 説明 |
| --- | --- | --- |
| `--lang` | (必須) | 言語コード |
| `--speed-threshold` | 1.0 | 速度調整の閾値 |
| `--debug` | - | デバッグモードを有効化 |
