.PHONY: build run clean help
.DEFAULT_GOAL := help

IMAGE_NAME := srt-tts

build: ## Dockerイメージをビルド
	docker build -t $(IMAGE_NAME) .

run: ## SRTファイルを音声化 (SRT=<path> LANG=<code> [JSON_ONLY=1] [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make run SRT=srt/example.srt LANG=ja)
endif
ifndef LANG
	$(error LANG is required. Usage: make run SRT=srt/example.srt LANG=ja (ja, en, ko, zh-CN, etc.))
endif
ifdef JSON_ONLY
	docker compose run --rm srt-tts python -m src.app /app/$(SRT) --lang $(LANG) --json-only $(ARGS)
else
	docker compose run --rm srt-tts python -m src.app /app/$(SRT) --lang $(LANG) $(ARGS)
endif

clean: ## Dockerイメージを削除
	docker rmi $(IMAGE_NAME) || true

help: ## ヘルプを表示
	@echo "SRT-TTS - SRTファイルをElevenLabs APIで音声化"
	@echo ""
	@echo "使用可能なコマンド:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "引数:"
	@echo "  SRT          入力SRTファイルのパス (例: srt/example.srt)"
	@echo "  LANG         言語コード (必須: ja, en, ko, zh-CN, ru, es, etc.)"
	@echo "  JSON_ONLY    1を指定するとTTSをスキップしてJSONのみ出力"
	@echo "  ARGS         追加の引数 (例: --gtts-only)"
	@echo ""
	@echo "追加オプション (ARGSで指定):"
	@echo "  --gtts-only                    gTTSのみで音声生成 (ElevenLabsを使用しない)"
	@echo "  --estimation-ratio <float>     gTTS事前見積もりの補正係数 (デフォルト: 1.0、0以下で無効)"
	@echo "  --gtts-shorten-retries <int>   gTTS事前見積もりでの再意訳リトライ回数 (デフォルト: 8)"
	@echo "  --el-shorten-retries <int>     ElevenLabs生成後の再意訳リトライ回数 (デフォルト: 2)"
	@echo "  --speed-threshold <float>      速度調整の閾値 (デフォルト: 0.9)"
	@echo "  --margin-ms <int>              エントリー間マージン (デフォルト: 100ms)"
	@echo ""
	@echo "使用例:"
	@echo "  make build"
	@echo "  make run SRT=srt/example.srt LANG=ja"
	@echo "  make run SRT=srt/example.srt LANG=en"
	@echo "  make run SRT=srt/example.srt LANG=ja JSON_ONLY=1"
	@echo "  make run SRT=srt/example.srt LANG=en ARGS='--gtts-only'"
