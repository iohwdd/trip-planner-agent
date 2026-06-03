from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from dataclasses import dataclass

try:
    import chromadb
except ImportError:  # pragma: no cover - optional until dependency install
    chromadb = None

try:
    from langchain_text_splitters import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )
except ImportError:  # pragma: no cover - optional until dependency install
    MarkdownHeaderTextSplitter = None
    RecursiveCharacterTextSplitter = None

try:
    from sentence_transformers import CrossEncoder, SentenceTransformer
except ImportError:  # pragma: no cover - optional until dependency install
    CrossEncoder = None
    SentenceTransformer = None

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional until dependency install
    PdfReader = None

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from planner.models import KnowledgeBaseRecord, KnowledgeDocumentRecord
from planner.services.object_storage import MinioObjectStorage
from planner.services.runtime_config import load_runtime_config

User = get_user_model()
_knowledge_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="knowledge-base")


def _safe_filename(file_name: str) -> str:
    original = (file_name or "").strip()
    if not original:
        return "document.txt"

    # Preserve human-readable names, including Chinese, and only strip unsafe path/control chars.
    normalized = re.sub(r"[\\/]+", "-", original)
    normalized = re.sub(r"[\x00-\x1f\x7f]+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    return normalized or "document.txt"


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    title: str
    document_id: str
    score: float
    heading_path: str = ""


class KnowledgeBaseService:
    DEFAULT_SLUG = "assistant-default"
    DEFAULT_NAME = "智能助手知识库"

    def __init__(self) -> None:
        self.config = load_runtime_config()
        self.object_storage = MinioObjectStorage(self.config.minio)
        self._embedding_model = None
        self._reranker_model = None
        self._chroma_client = None
        self._active_documents: set[str] = set()
        self._active_documents_lock = threading.Lock()

    def get_default_knowledge_base(self, *, actor: User | None = None) -> dict:
        record = self._ensure_default_base(actor=actor)
        return self._base_to_payload(record)

    def list_documents(self) -> list[dict]:
        base = self._ensure_default_base()
        return [
            self._document_to_payload(record)
            for record in base.document_records.order_by("-updated_at", "-created_at")
        ]

    def get_dashboard_payload(self, *, actor: User | None = None) -> dict:
        base = self._ensure_default_base(actor=actor)
        documents = self.list_documents()
        ready_count = sum(
            1
            for item in documents
            if item["status"] == KnowledgeDocumentRecord.STATUS_READY
        )
        processing_count = sum(
            1
            for item in documents
            if item["status"]
            in {
                KnowledgeDocumentRecord.STATUS_PENDING,
                KnowledgeDocumentRecord.STATUS_PROCESSING,
            }
        )
        failed_count = sum(
            1
            for item in documents
            if item["status"] == KnowledgeDocumentRecord.STATUS_FAILED
        )
        return {
            "knowledge_base": self._base_to_payload(base),
            "documents": documents,
            "summary": {
                "document_count": len(documents),
                "ready_count": ready_count,
                "processing_count": processing_count,
                "failed_count": failed_count,
            },
        }

    def get_overview_payload(self, *, actor: User | None = None) -> dict:
        base = self._ensure_default_base(actor=actor)
        aggregates = base.document_records.aggregate(
            document_count=Count("document_id"),
            indexed_document_count=Count(
                "document_id",
                filter=Q(status=KnowledgeDocumentRecord.STATUS_READY),
            ),
            total_file_size_bytes=Sum("file_size_bytes"),
        )
        total_size_bytes = int(aggregates.get("total_file_size_bytes") or 0)
        return {
            "knowledge_base": self._base_to_payload(base),
            "document_count": int(aggregates.get("document_count") or 0),
            "indexed_document_count": int(
                aggregates.get("indexed_document_count") or 0
            ),
            "total_file_size_bytes": total_size_bytes,
            "total_file_size_label": self._format_file_size(total_size_bytes),
        }

    def upload_document(
        self,
        *,
        file_name: str,
        content_type: str,
        file_bytes: bytes,
        actor: User,
    ) -> dict:
        normalized_name = _safe_filename(file_name)
        extension = normalized_name.rsplit(".", 1)[-1].lower() if "." in normalized_name else ""
        if extension not in {"md", "txt", "pdf"}:
            raise ValueError("当前仅支持 md、txt 和 pdf 文档。")
        if not file_bytes:
            raise ValueError("上传文件不能为空。")

        base = self._ensure_default_base(actor=actor)
        mime_type = content_type or self._infer_content_type(extension)

        with transaction.atomic():
            document = KnowledgeDocumentRecord.objects.create(
                knowledge_base=base,
                title=normalized_name.rsplit(".", 1)[0] or normalized_name,
                file_name=normalized_name,
                mime_type=mime_type,
                object_key=f"knowledge/{base.knowledge_base_id}/{KnowledgeDocumentRecord().document_id}/{normalized_name}",
                file_size_bytes=len(file_bytes),
                status=KnowledgeDocumentRecord.STATUS_PENDING,
                status_detail="文件已上传，等待解析",
                progress_percent=5,
            )
            document.object_key = (
                f"knowledge/{base.knowledge_base_id}/{document.document_id}/{normalized_name}"
            )
            document.save(update_fields=["object_key"])

        try:
            self.object_storage.upload_bytes(
                object_key=document.object_key,
                data=file_bytes,
                content_type=mime_type,
            )
        except Exception as exc:
            self._mark_document_failed(document, str(exc))
            raise

        self._submit_document_processing(document.document_id)
        document.refresh_from_db()
        return self._document_to_payload(document)

    def delete_document(self, document_id: str) -> bool:
        document = KnowledgeDocumentRecord.objects.filter(document_id=document_id).first()
        if document is None:
            return False
        self._delete_index(document)
        self.object_storage.delete_object(object_key=document.object_key)
        document.delete()
        return True

    def reindex_all(self) -> dict:
        base = self._ensure_default_base()
        documents = list(base.document_records.order_by("created_at"))
        queued = 0
        for document in documents:
            if self._is_document_active(document.document_id):
                continue
            self._queue_document(
                document,
                detail="已加入重建队列",
                progress=5,
                clear_error=True,
                reset_chunks=True,
            )
            if self._submit_document_processing(document.document_id):
                queued += 1

        return {
            "queued": queued,
            "document_count": len(documents),
        }

    def retry_document(self, document_id: str) -> dict | None:
        document = KnowledgeDocumentRecord.objects.filter(document_id=document_id).first()
        if document is None:
            return None
        if self._is_document_active(document.document_id):
            return self._document_to_payload(document)
        self._queue_document(
            document,
            detail="已重新加入解析队列",
            progress=5,
            clear_error=True,
            reset_chunks=True,
        )
        self._submit_document_processing(document.document_id)
        document.refresh_from_db()
        return self._document_to_payload(document)

    def retrieve(self, query: str, *, limit: int | None = None) -> list[RetrievedChunk]:
        query_text = (query or "").strip()
        if not query_text:
            return []
        base = KnowledgeBaseRecord.objects.filter(is_default=True).first()
        if base is None or not base.document_records.filter(status=KnowledgeDocumentRecord.STATUS_READY).exists():
            return []
        if chromadb is None or SentenceTransformer is None:
            return []

        collection = self._get_collection(base.slug)
        if collection.count() == 0:
            return []

        top_k = limit or self.config.knowledge.retrieval_k
        query_embedding = self._get_embedding_model().encode(
            [query_text],
            normalize_embeddings=True,
        )[0].tolist()
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"knowledge_base_id": base.knowledge_base_id},
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        if not documents:
            return []

        chunks = [
            RetrievedChunk(
                content=content,
                title=(metadata or {}).get("title", ""),
                document_id=(metadata or {}).get("document_id", ""),
                heading_path=(metadata or {}).get("heading_path", ""),
                score=float(-(distances[index] if index < len(distances) else 0.0)),
            )
            for index, (content, metadata) in enumerate(zip(documents, metadatas))
        ]
        return self._rerank(query_text, chunks)[: self.config.knowledge.rerank_top_n]

    def _ensure_default_base(self, *, actor: User | None = None) -> KnowledgeBaseRecord:
        base = KnowledgeBaseRecord.objects.filter(is_default=True).first()
        if base is not None:
            return base
        with transaction.atomic():
            base = KnowledgeBaseRecord.objects.filter(is_default=True).select_for_update().first()
            if base is not None:
                return base
            return KnowledgeBaseRecord.objects.create(
                name=self.DEFAULT_NAME,
                slug=self.DEFAULT_SLUG,
                description="仅用于增强智能助手回答的默认知识库。",
                is_default=True,
                status=KnowledgeBaseRecord.STATUS_READY,
            )

    def _build_document_chunks(
        self, *, file_name: str, content: str
    ) -> list[dict[str, str | int]]:
        return self._split_document(file_name, content)

    def _index_document_chunks(
        self, *, document: KnowledgeDocumentRecord, chunks: list[dict[str, str | int]]
    ) -> int:
        if not chunks:
            raise RuntimeError("文档切分后没有可索引内容。")

        texts = [item["content"] for item in chunks]
        embeddings = self._get_embedding_model().encode(
            texts,
            normalize_embeddings=True,
        ).tolist()
        collection = self._get_collection(document.knowledge_base.slug)
        collection.delete(where={"document_id": document.document_id})
        collection.upsert(
            ids=[item["chunk_id"] for item in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "knowledge_base_id": document.knowledge_base_id,
                    "document_id": document.document_id,
                    "title": document.title,
                    "file_name": document.file_name,
                    "heading_path": item["heading_path"],
                    "chunk_index": item["chunk_index"],
                }
                for item in chunks
            ],
        )
        return len(chunks)

    def _split_document(self, file_name: str, content: str) -> list[dict]:
        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "txt"
        chunks: list[dict] = []
        if extension == "md" and MarkdownHeaderTextSplitter is not None:
            header_splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=[
                    ("#", "h1"),
                    ("##", "h2"),
                    ("###", "h3"),
                ]
            )
            documents = header_splitter.split_text(content)
            for section_index, document in enumerate(documents):
                section_text = document.page_content.strip()
                if not section_text:
                    continue
                heading_path = " / ".join(
                    value for value in (
                        document.metadata.get("h1"),
                        document.metadata.get("h2"),
                        document.metadata.get("h3"),
                    ) if value
                )
                for chunk_index, text in enumerate(self._recursive_split(section_text)):
                    chunks.append(
                        {
                            "chunk_id": f"{section_index}-{chunk_index}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:10]}",
                            "content": text,
                            "heading_path": heading_path,
                            "chunk_index": len(chunks),
                        }
                    )
        else:
            for chunk_index, text in enumerate(self._recursive_split(content)):
                chunks.append(
                    {
                        "chunk_id": f"plain-{chunk_index}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:10]}",
                        "content": text,
                        "heading_path": "",
                        "chunk_index": chunk_index,
                    }
                )
        return chunks

    def _recursive_split(self, text: str) -> list[str]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []
        if RecursiveCharacterTextSplitter is None:
            return [cleaned]
        splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " "],
            chunk_size=self.config.knowledge.chunk_size,
            chunk_overlap=self.config.knowledge.chunk_overlap,
            length_function=len,
        )
        return [item.strip() for item in splitter.split_text(cleaned) if item.strip()]

    def _process_document(self, *, document: KnowledgeDocumentRecord, file_bytes: bytes | None = None) -> None:
        self._set_document_processing(document, detail="正在读取文档", progress=12)
        source_bytes = file_bytes or self.object_storage.download_bytes(object_key=document.object_key)
        self._set_document_processing(document, detail="正在解析正文", progress=36)
        extracted_content = self._extract_document_text(
            file_name=document.file_name,
            file_bytes=source_bytes,
        )
        self._set_document_processing(document, detail="正在切分内容", progress=58)
        chunks = self._build_document_chunks(
            file_name=document.file_name,
            content=extracted_content,
        )
        self._set_document_processing(document, detail="正在生成向量", progress=76)
        chunk_count = self._index_document_chunks(document=document, chunks=chunks)
        self._set_document_processing(document, detail="正在写入索引", progress=92)
        document.chunk_count = chunk_count
        document.status = KnowledgeDocumentRecord.STATUS_READY
        document.status_detail = "索引已完成"
        document.progress_percent = 100
        document.error_message = ""
        document.save(
            update_fields=[
                "chunk_count",
                "status",
                "status_detail",
                "progress_percent",
                "error_message",
                "updated_at",
            ]
        )

    def _rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks or CrossEncoder is None:
            return chunks
        model = self._get_reranker_model()
        if model is None:
            return chunks
        pairs = [[query, item.content] for item in chunks]
        scores = model.predict(pairs)
        reranked = [
            RetrievedChunk(
                content=item.content,
                title=item.title,
                document_id=item.document_id,
                heading_path=item.heading_path,
                score=float(score),
            )
            for item, score in zip(chunks, scores)
        ]
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def _delete_index(self, document: KnowledgeDocumentRecord) -> None:
        if chromadb is None:
            return
        collection = self._get_collection(document.knowledge_base.slug)
        collection.delete(where={"document_id": document.document_id})

    def _set_document_processing(
        self,
        document: KnowledgeDocumentRecord,
        *,
        detail: str,
        progress: int,
    ) -> None:
        document.status = KnowledgeDocumentRecord.STATUS_PROCESSING
        document.status_detail = detail[:160]
        document.progress_percent = max(0, min(99, int(progress)))
        document.error_message = ""
        document.save(
            update_fields=[
                "status",
                "status_detail",
                "progress_percent",
                "error_message",
                "updated_at",
            ]
        )

    def _mark_document_failed(self, document: KnowledgeDocumentRecord, message: str) -> None:
        document.status = KnowledgeDocumentRecord.STATUS_FAILED
        document.status_detail = "处理失败"
        document.progress_percent = 0
        document.error_message = message[:2000]
        document.save(
            update_fields=[
                "status",
                "status_detail",
                "progress_percent",
                "error_message",
                "updated_at",
            ]
        )

    def _queue_document(
        self,
        document: KnowledgeDocumentRecord,
        *,
        detail: str,
        progress: int = 0,
        clear_error: bool = False,
        reset_chunks: bool = False,
    ) -> None:
        document.status = KnowledgeDocumentRecord.STATUS_PENDING
        document.status_detail = detail[:160]
        document.progress_percent = max(0, min(100, int(progress)))
        if clear_error:
            document.error_message = ""
        if reset_chunks:
            document.chunk_count = 0
        update_fields = ["status", "status_detail", "progress_percent", "updated_at"]
        if clear_error:
            update_fields.append("error_message")
        if reset_chunks:
            update_fields.append("chunk_count")
        document.save(update_fields=update_fields)

    def _submit_document_processing(self, document_id: str) -> bool:
        with self._active_documents_lock:
            if document_id in self._active_documents:
                return False
            self._active_documents.add(document_id)
        try:
            _knowledge_executor.submit(self._run_document_processing, document_id)
        except Exception:
            with self._active_documents_lock:
                self._active_documents.discard(document_id)
            raise
        return True

    def _is_document_active(self, document_id: str) -> bool:
        with self._active_documents_lock:
            return document_id in self._active_documents

    def _run_document_processing(self, document_id: str) -> None:
        close_old_connections()
        try:
            document = KnowledgeDocumentRecord.objects.select_related(
                "knowledge_base"
            ).filter(document_id=document_id).first()
            if document is None:
                return
            try:
                self._process_document(document=document)
            except Exception as exc:
                self._mark_document_failed(document, str(exc))
        finally:
            with self._active_documents_lock:
                self._active_documents.discard(document_id)
            close_old_connections()

    def _get_collection(self, slug: str):
        client = self._get_chroma_client()
        return client.get_or_create_collection(
            name=f"{self.config.knowledge.collection_prefix}-{slug}"
        )

    def _get_chroma_client(self):
        if self._chroma_client is not None:
            return self._chroma_client
        if chromadb is None:
            raise RuntimeError("chromadb 未安装，无法使用知识库索引。")
        self._chroma_client = chromadb.PersistentClient(
            path=self.config.knowledge.persist_directory
        )
        return self._chroma_client

    def _get_embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers 未安装，无法加载 embedding 模型。")
        self._embedding_model = SentenceTransformer(self.config.knowledge.embedding_model)
        return self._embedding_model

    def _get_reranker_model(self):
        if self._reranker_model is not None:
            return self._reranker_model
        if CrossEncoder is None:
            return None
        self._reranker_model = CrossEncoder(self.config.knowledge.reranker_model)
        return self._reranker_model

    @staticmethod
    def _infer_content_type(extension: str) -> str:
        if extension == "pdf":
            return "application/pdf"
        if extension == "md":
            return "text/markdown"
        return "text/plain"

    def _extract_document_text(self, *, file_name: str, file_bytes: bytes) -> str:
        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "txt"
        if extension == "pdf":
            return self._extract_pdf_text(file_bytes)
        return self._extract_text_document(file_bytes)

    @staticmethod
    def _extract_text_document(file_bytes: bytes) -> str:
        return file_bytes.decode("utf-8")

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        if PdfReader is None:
            raise RuntimeError("pypdf 未安装，暂时无法处理 pdf 文档。")

        reader = PdfReader(BytesIO(file_bytes))
        pages: list[str] = []
        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            visual_placeholders = self._extract_pdf_visual_blocks(page, page_index=page_index)
            if text:
                pages.append(text)
            if visual_placeholders:
                pages.extend(visual_placeholders)

        extracted = "\n\n".join(block for block in pages if block).strip()
        if extracted:
            return extracted
        raise ValueError("当前仅支持带文本层的 pdf，纯扫描图片型 pdf 暂时无法建立索引。")

    def _extract_pdf_visual_blocks(self, _page, *, page_index: int) -> list[str]:
        # Reserved for future OCR / figure-caption extraction so image-rich PDFs
        # can contribute structured text during vectorization.
        _ = page_index
        return []

    @staticmethod
    def _base_to_payload(record: KnowledgeBaseRecord) -> dict:
        return {
            "knowledge_base_id": record.knowledge_base_id,
            "name": record.name,
            "slug": record.slug,
            "description": record.description,
            "status": record.status,
            "is_default": record.is_default,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    @staticmethod
    def _document_to_payload(record: KnowledgeDocumentRecord) -> dict:
        return {
            "document_id": record.document_id,
            "knowledge_base_id": record.knowledge_base_id,
            "title": record.title,
            "file_name": record.file_name,
            "mime_type": record.mime_type,
            "file_size_bytes": record.file_size_bytes,
            "status": record.status,
            "status_detail": record.status_detail,
            "progress_percent": record.progress_percent,
            "chunk_count": record.chunk_count,
            "error_message": record.error_message,
            "updated_at": record.updated_at,
            "created_at": record.created_at,
        }

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        value = float(max(0, size_bytes))
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024


knowledge_base_service = KnowledgeBaseService()
