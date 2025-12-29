.PHONY: build run clean help

IMAGE_NAME := srt-tts

## Dockerイメージをビルド
build:
	docker build -t $(IMAGE_NAME) .

## SRTファイルを音声化（使用例: make run SRT=srt/example.srt）
run:
ifndef SRT
	$(error SRT is required. Usage: make run SRT=srt/example.srt)
endif
	docker compose run --rm srt-tts python -m src.app /app/$(SRT)

## Dockerイメージを削除
clean:
	docker rmi $(IMAGE_NAME) || true

## ヘルプを表示
help:
	@echo "使用可能なコマンド:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /'
