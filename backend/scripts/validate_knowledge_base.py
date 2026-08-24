from __future__ import annotations

from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.knowledge_validation import validate_knowledge_base


def main() -> int:
    """运行知识库一致性校验，并以进程状态码表示成功或失败。

    Returns:
        int: 无一致性问题时为 ``0``，发现问题时为 ``1``。
    """
    errors = validate_knowledge_base()
    if errors:
        print("知识库一致性校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("知识库一致性校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
