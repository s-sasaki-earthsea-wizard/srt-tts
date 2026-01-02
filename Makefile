.PHONY: build run clean help
.DEFAULT_GOAL := help

IMAGE_NAME := srt-tts

build: ## Dockerイメージをビルド
	docker build -t $(IMAGE_NAME) .

run: ## SRTファイルを音声化 (SRT=<path> [JSON_ONLY=1] [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make run SRT=srt/example.srt)
endif
ifdef JSON_ONLY
	docker compose run --rm srt-tts python -m src.app /app/$(SRT) --json-only $(ARGS)
else
	docker compose run --rm srt-tts python -m src.app /app/$(SRT) $(ARGS)
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
	@echo "  ARGS         追加の引数 (例: --gtts-only)"
	@echo ""
	@echo "追加オプション (ARGSで指定):"
	@echo "  --gtts-only                    gTTSのみで音声生成 (ElevenLabsを使用しない)"
	@echo "  --lang <code>                  gTTSの言語コード (デフォルト: ja、例: en, ko, zh-CN, ru, es)"
	@echo "  --estimation-ratio <float>     gTTS事前見積もりの補正係数 (デフォルト: 0.9、0以下で無効)"
	@echo "  --gtts-shorten-retries <int>   gTTS事前見積もりでの再意訳リトライ回数 (デフォルト: 8)"
	@echo "  --el-shorten-retries <int>     ElevenLabs生成後の再意訳リトライ回数 (デフォルト: 2)"
	@echo "  --speed-threshold <float>      速度調整の閾値 (デフォルト: 1.0)"
	@echo "  --margin-ms <int>              エントリー間マージン (デフォルト: 100ms)"
	@echo ""
	@echo "使用例:"
	@echo "  make build"
	@echo "  make run SRT=srt/example.srt"
	@echo "  make run SRT=srt/example.srt JSON_ONLY=1"
	@echo "  make run SRT=srt/example.srt ARGS='--gtts-only'"
	@echo "  make run SRT=srt/example.srt ARGS='--gtts-only --lang en'"
