.PHONY: setup run run-dir dub dub-audio synth help
.DEFAULT_GOAL := help

# LANG doubles as the shell locale variable (e.g. C.UTF-8), so `ifndef LANG`
# alone never fires. Reject locale-looking values explicitly.
check_lang = $(if $(findstring .,$(LANG)),$(error LANG looks like a shell locale ($(LANG)); pass a language code, e.g. LANG=en))

setup: ## uvで依存パッケージをインストール
	uv sync

run: ## SRTファイルを音声化 (SRT=<path> LANG=<code> [JSON_ONLY=1] [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make run SRT=srt/example.srt LANG=ja)
endif
ifndef LANG
	$(error LANG is required. Usage: make run SRT=srt/example.srt LANG=ja (ja, en, ko, zh-CN, etc.))
endif
	$(check_lang)
ifdef JSON_ONLY
	uv run python -m src.app $(SRT) --lang $(LANG) --json-only $(ARGS)
else
	uv run python -m src.app $(SRT) --lang $(LANG) $(ARGS)
endif

run-dir: ## ディレクトリ内の全SRTファイルを音声化 (DIR=<path> [ARGS=...])
ifndef DIR
	$(error DIR is required. Usage: make run-dir DIR=srt/AI-weather-forecast)
endif
	@echo "処理対象ディレクトリ: $(DIR)"
	@for file in $(DIR)/*-*.srt; do \
		if [ -f "$$file" ]; then \
			lang=$$(basename "$$file" .srt | rev | cut -d'-' -f1 | rev); \
			echo ""; \
			echo "========================================"; \
			echo "処理中: $$file (言語: $$lang)"; \
			echo "========================================"; \
			uv run python -m src.app $$file --lang $$lang $(ARGS); \
		fi \
	done
	@echo ""
	@echo "全ファイルの処理が完了しました"

dub: ## 日本語SRTから吹き替え用SRTを生成 (SRT=<path> LANG=<code> [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make dub SRT=srt/example-jp.srt LANG=en)
endif
ifndef LANG
	$(error LANG is required. Usage: make dub SRT=srt/example-jp.srt LANG=en)
endif
	$(check_lang)
	uv run python -m src.dub $(SRT) --lang $(LANG) $(ARGS)

dub-audio: ## 日本語SRTから吹き替え用SRT+音声を生成 (SRT=<path> LANG=<code> [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make dub-audio SRT=srt/example-jp.srt LANG=en)
endif
ifndef LANG
	$(error LANG is required. Usage: make dub-audio SRT=srt/example-jp.srt LANG=en)
endif
	$(check_lang)
	uv run python -m src.dub $(SRT) --lang $(LANG) --gtts-only $(ARGS)

synth: ## 既存SRTからgTTSで音声を生成 (SRT=<path> LANG=<code> [ARGS=...])
ifndef SRT
	$(error SRT is required. Usage: make synth SRT=srt/example-en.srt LANG=en)
endif
ifndef LANG
	$(error LANG is required. Usage: make synth SRT=srt/example-en.srt LANG=en)
endif
	$(check_lang)
	uv run python -m src.synth $(SRT) --lang $(LANG) $(ARGS)

help: ## ヘルプを表示
	@echo "SRT-TTS - SRTファイルを音声化 (既定: ローカルのVoxCPM2、オプション: ElevenLabs / gTTS)"
	@echo ""
	@echo "使用可能なコマンド:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "引数:"
	@echo "  SRT          入力SRTファイルのパス (例: srt/example.srt)"
	@echo "  LANG         言語コード (必須: ja, en, ko, zh-CN, ru, es, etc.)"
	@echo "  DIR          処理対象ディレクトリ (例: srt/AI-weather-forecast)"
	@echo "  JSON_ONLY    1を指定するとTTSをスキップしてJSONのみ出力"
	@echo "  ARGS         追加の引数 (例: --gtts-only)"
	@echo ""
	@echo "参照音声 (VoxCPM):"
	@echo "  voices/<lang>/reference.{wav,mp3,flac} と reference.txt (書き起こし) を置くと声を複製"
	@echo "  zh-CN や pt-BR は voices/zh, voices/pt にフォールバック。参照音声がなければ毎回声が変わりうる"
	@echo ""
	@echo "追加オプション (ARGSで指定):"
	@echo "  --tts-provider <name>          音声合成エンジン: voxcpm (既定、ローカル) / elevenlabs (有料API)"
	@echo "  --tags                         LLMでElevenLabs用オーディオタグを付与 (既定: 無効)"
	@echo "  --gtts-only                    gTTSのみで音声生成 (VoxCPM/ElevenLabsを使用しない)"
	@echo "  --estimation-ratio <float>     gTTS事前見積もりの補正係数 (デフォルト: 1.0、0以下で無効)"
	@echo "  --gtts-shorten-retries <int>   gTTS事前見積もりでの再意訳リトライ回数 (デフォルト: 6)"
	@echo "  --tts-shorten-retries <int>    音声合成後の再意訳リトライ回数 (デフォルト: 6)"
	@echo "  --speed-threshold <float>      速度調整の閾値 (デフォルト: 1.0)"
	@echo "  --shorten-ratio <float>        文字数削減の目標係数 (デフォルト: 0.95)"
	@echo "  --margin-ms <int>              エントリー間マージン (デフォルト: 100ms)"
	@echo ""
	@echo "使用例:"
	@echo "  make setup"
	@echo "  make run SRT=srt/example.srt LANG=ja"
	@echo "  make run SRT=srt/example.srt LANG=en"
	@echo "  make run SRT=srt/example.srt LANG=ja JSON_ONLY=1"
	@echo "  make run SRT=srt/example.srt LANG=en ARGS='--tts-provider elevenlabs --tags'"
	@echo "  make run SRT=srt/example.srt LANG=en ARGS='--gtts-only'"
	@echo "  make run-dir DIR=srt/AI-weather-forecast"
	@echo "  make run-dir DIR=srt/AI-weather-forecast ARGS='--gtts-only'"
	@echo ""
	@echo "吹き替え脚本生成:"
	@echo "  make dub SRT=srt/example-jp.srt LANG=en           # 日本語SRTから英語吹き替えSRTを生成"
	@echo "  make dub-audio SRT=srt/example-jp.srt LANG=en     # 日本語SRTから英語吹き替えSRT+音声を生成"
	@echo "  make synth SRT=srt/example-en.srt LANG=en         # 既存SRTから音声のみ生成"
