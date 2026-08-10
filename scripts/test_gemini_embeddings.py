import asyncio

from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.base import cosine_similarity


async def main() -> None:
    provider = create_embedding_provider("gemini")
    try:
        vectors = await provider.embed_texts(
            [
                "Solar batteries store energy.",
                "Energy storage can use batteries.",
            ]
        )
        print(f"model={provider.model_name}")
        print(f"vector_dimension={len(vectors[0])}")
        print(
            "sample_similarity="
            f"{cosine_similarity(vectors[0], vectors[1]):.6f}"
        )
    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
