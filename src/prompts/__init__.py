"""プロンプト管理モジュール"""

from pathlib import Path


def load_prompt(name: str) -> str:
    """
    プロンプトファイルを読み込む

    Args:
        name: プロンプト名（拡張子なし）

    Returns:
        プロンプトの内容
    """
    prompt_dir = Path(__file__).parent
    prompt_path = prompt_dir / f"{name}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"プロンプトファイルが見つかりません: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")
