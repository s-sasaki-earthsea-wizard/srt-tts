# SRT-TTS

## プロジェクト概要

SRTファイルをElevenLabs APIで音声化するツール。LLMを使用してオーディオタグを自動付与し、より表現豊かな音声を生成する。

### 技術スタック

- Python 3.11+
- Docker / Docker Compose
- ElevenLabs TTS API (v3)
- OpenAI互換 LLM API
- pydub（音声処理）
- pysrt（SRTパース）

### アーキテクチャ

```text
SRTファイル
    ↓
[SRTパーサー] タイムスタンプ・テキスト抽出
    ↓
[LLM] オーディオタグ付与（前後2エントリーのコンテキスト参照）
    ↓
[ElevenLabs TTS] 音声合成
    ↓
[音声処理] 速度調整（タイムスタンプに収まるように）
    ↓
[音声結合] 最終MP3ファイル生成
```

## 言語設定

このプロジェクトでは**日本語**での応答を行ってください。コード内のコメント、ログメッセージ、エラーメッセージ、ドキュメンテーション文字列なども日本語で記述してください。

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

**重要**: Claude Codeを使用してコミットする場合は、必ず以下の署名を含める：

```text
🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
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
- [x] Dockerボリュームマウント（開発用）
