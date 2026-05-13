from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from anibot.rag.ingest import ingest_knowledge


if __name__ == "__main__":
    result = ingest_knowledge(ROOT)
    print(
        f"Indexed {result['documents']} documents into {result['chunks']} chunks "
        f"(chroma_enabled={result['chroma_enabled']})."
    )
