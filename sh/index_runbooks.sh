#!/usr/bin/env bash
#
# data/runbooks/*.md를 ChromaDB에 인덱싱하는 스크립트.
# 에이전트 기동 전에 최초 1회 실행하면 된다.
#
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x ".venv/bin/python3" ] && export PATH="$PWD/.venv/bin:$PATH"

python3 -c "
from agent.rag import index_runbooks
count = index_runbooks()
print(f'인덱싱 완료: {count}개 청크 저장됨')
"
