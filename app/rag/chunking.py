import hashlib
from urllib.parse import urlsplit, urlunsplit

from app.schemas.rag import (
    ChunkMetadata,
    DocumentChunk,
    IndexSource,
)


class DocumentChunker:
    def __init__(self, *, chunk_size: int, overlap: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if overlap < 0:
            raise ValueError("overlap must not be negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, source: IndexSource) -> list[DocumentChunk]:
        content = source.content
        chunks: list[DocumentChunk] = []
        start = self._skip_whitespace(content, 0)

        while start < len(content):
            end = self._find_end(content, start)
            while end > start and content[end - 1].isspace():
                end -= 1
            if end <= start:
                end = min(start + self.chunk_size, len(content))

            text = content[start:end]
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            chunk_index = len(chunks)
            chunk_id = self._chunk_id(
                source=source,
                chunk_index=chunk_index,
                content_hash=content_hash,
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    source_id=source.source_id,
                    source_url=source.source_url,
                    text=text,
                    metadata=ChunkMetadata(
                        title=source.title,
                        section=source.section,
                        location=source.location,
                        content_hash=content_hash,
                        chunk_index=chunk_index,
                        char_start=start,
                        char_end=end,
                    ),
                )
            )
            if end >= len(content):
                break
            start = self._next_start(content, current_start=start, end=end)

        return chunks

    def _find_end(self, content: str, start: int) -> int:
        limit = min(start + self.chunk_size, len(content))
        if limit >= len(content):
            return len(content)
        if content[limit - 1].isspace() or content[limit].isspace():
            return limit

        boundary = max(
            content.rfind(" ", start + 1, limit),
            content.rfind(chr(10), start + 1, limit),
            content.rfind(chr(9), start + 1, limit),
        )
        return boundary if boundary > start else limit

    def _next_start(
        self,
        content: str,
        *,
        current_start: int,
        end: int,
    ) -> int:
        if self.overlap == 0:
            return self._skip_whitespace(content, end)

        next_start = max(current_start + 1, end - self.overlap)
        if (
            next_start < len(content)
            and next_start > current_start
            and not content[next_start].isspace()
            and not content[next_start - 1].isspace()
        ):
            while (
                next_start > current_start
                and not content[next_start - 1].isspace()
            ):
                next_start -= 1

        if next_start <= current_start:
            next_start = current_start + 1
            while (
                next_start < end
                and not content[next_start - 1].isspace()
            ):
                next_start += 1
        return self._skip_whitespace(content, next_start)

    @staticmethod
    def _skip_whitespace(content: str, start: int) -> int:
        while start < len(content) and content[start].isspace():
            start += 1
        return start

    @staticmethod
    def _chunk_id(
        *,
        source: IndexSource,
        chunk_index: int,
        content_hash: str,
    ) -> str:
        url_parts = urlsplit(str(source.source_url))
        canonical_url = urlunsplit(
            (
                url_parts.scheme.casefold(),
                url_parts.netloc.casefold(),
                url_parts.path,
                url_parts.query,
                "",
            )
        )
        identity = "|".join(
            (
                source.source_id,
                canonical_url,
                source.section or "",
                source.location or "",
                str(chunk_index),
                content_hash,
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"chunk-{digest}"


def chunk_document(
    source: IndexSource,
    *,
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
    return DocumentChunker(
        chunk_size=chunk_size,
        overlap=overlap,
    ).chunk(source)


def chunk_text(
    text: str,
    *,
    source_id: str,
    source_url: str,
    title: str,
    chunk_size: int,
    overlap: int,
    section: str | None = None,
    location: str | None = None,
) -> list[DocumentChunk]:
    return chunk_document(
        IndexSource(
            source_id=source_id,
            source_url=source_url,
            title=title,
            content=text,
            section=section,
            location=location,
        ),
        chunk_size=chunk_size,
        overlap=overlap,
    )
