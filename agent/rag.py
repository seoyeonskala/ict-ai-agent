"""런북 RAG — ChromaDB 기반 벡터 검색.

인덱싱: index_runbooks()로 data/runbooks/*.md를 청크 분할 → 임베딩 → 저장.
검색:   search_runbooks(query)로 유사도 높은 청크를 반환.
"""
import re
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
COLLECTION_NAME = "runbooks"

_embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn,
    )


def _chunk_markdown(text: str, source: str) -> list[dict]:
    """마크다운을 제목 기준 또는 번호 절차 단위로 청크 분할."""
    lines = text.strip().splitlines()
    chunks = []
    title = source
    if lines and lines[0].startswith("#"):
        title = lines[0].lstrip("# ").strip()
        lines = lines[1:]

    body = "\n".join(lines).strip()
    steps = re.split(r"(?=^\d+\.)", body, flags=re.MULTILINE)
    steps = [s.strip() for s in steps if s.strip()]

    if len(steps) <= 1:
        chunks.append({"text": f"{title}\n{body}", "source": source})
    else:
        for step in steps:
            chunks.append({"text": f"{title} — {step}", "source": source})

    return chunks


def index_runbooks() -> int:
    """data/runbooks/*.md 파일을 청크로 나눠 ChromaDB에 저장. 기존 데이터는 초기화."""
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_embedding_fn,
    )

    runbook_dir = DATA_DIR / "runbooks"
    all_chunks = []
    for md_file in sorted(runbook_dir.glob("*.md")):
        text = md_file.read_text()
        chunks = _chunk_markdown(text, md_file.stem)
        all_chunks.extend(chunks)

    if not all_chunks:
        return 0

    collection.add(
        ids=[f"chunk-{i}" for i in range(len(all_chunks))],
        documents=[c["text"] for c in all_chunks],
        metadatas=[{"source": c["source"]} for c in all_chunks],
    )
    return len(all_chunks)


def search_runbooks(query: str, n_results: int = 3) -> list[dict]:
    """쿼리와 유사한 런북 청크를 검색해 반환."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[query], n_results=n_results)
    out = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        out.append({
            "text": doc,
            "source": meta["source"],
            "score": round(1 - dist, 4),
        })
    return out
