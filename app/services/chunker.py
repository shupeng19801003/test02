from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.config import settings
from app.services.document_processor import DocumentSection


def chunk_sections(sections: list[DocumentSection]) -> list[DocumentSection]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。", ".", " ", ""],
    )

    chunks = []
    for section in sections:
        texts = splitter.split_text(section.text)
        for i, text in enumerate(texts):
            chunks.append(DocumentSection(
                text=text,
                metadata={**section.metadata, "chunk_index": i},
            ))

    return chunks
