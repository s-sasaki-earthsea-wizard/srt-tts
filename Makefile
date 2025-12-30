.PHONY: build run clean help
.DEFAULT_GOAL := help

IMAGE_NAME := srt-tts

build: ## Dockerイメージをビルド
	docker build -t $(IMAGE_NAME) .

run: ## SRTファイルを音声化 (SRT=<path> [JSON_ONLY=1])
ifndef SRT
	$(error SRT is required. Usage: make run SRT=srt/example.srt)
endif
ifdef JSON_ONLY
	docker compose run --rm srt-tts python -m src.app /app/$(SRT) --json-only
else
	docker compose run --rm srt-tts python -m src.app /app/$(SRT)
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
	@echo "  JSON_ONLY    1を指定するとTTSをスキップしてJSONのみ出力"
	@echo ""
	@echo "使用例:"
	@echo "  make build"
	@echo "  make run SRT=srt/example.srt"
	@echo "  make run SRT=srt/example.srt JSON_ONLY=1"
