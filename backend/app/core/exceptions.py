"""Domain-specific exceptions, mapped to HTTP responses in app.core.error_handlers.

Each subclass also carries a taxonomy_category, drawn from a fixed
vocabulary (input, intent, planner, tool, retriever, memory, prompt,
reasoning, output, deployment) describing *where in the pipeline* the
failure originated — independent of its HTTP status code. Logged
alongside every error (see error_handlers.py) and used by
eval/metrics_report.py to break down error rates by category. Not every
category has a corresponding exception today (e.g. "intent"/"planner"/
"memory" have no failure mode yet, since routing and history handling
can't currently raise) — the vocabulary is fixed, its usage isn't.
"""


class AppError(Exception):
    status_code: int = 500
    taxonomy_category: str = "output"
    error_code: str = "APP_ERROR"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class UnauthorizedError(AppError):
    status_code = 401
    taxonomy_category = "input"
    error_code = "UNAUTHORIZED"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    taxonomy_category = "input"
    error_code = "UNSUPPORTED_FILE_TYPE"


class EmptyFileError(AppError):
    status_code = 400
    taxonomy_category = "input"
    error_code = "EMPTY_FILE"


class FileTooLargeError(AppError):
    status_code = 413
    taxonomy_category = "input"
    error_code = "FILE_TOO_LARGE"


class DocumentNotFoundError(AppError):
    status_code = 404
    taxonomy_category = "input"
    error_code = "DOCUMENT_NOT_FOUND"


class ConfirmationRequiredError(AppError):
    status_code = 400
    taxonomy_category = "input"
    error_code = "CONFIRMATION_REQUIRED"


class CorruptedPDFError(AppError):
    status_code = 422
    taxonomy_category = "input"
    error_code = "CORRUPTED_PDF"


class TextExtractionError(AppError):
    status_code = 500
    taxonomy_category = "tool"
    error_code = "TEXT_EXTRACTION_ERROR"


class EmbeddingModelLoadError(AppError):
    status_code = 500
    taxonomy_category = "deployment"
    error_code = "EMBEDDING_MODEL_LOAD_ERROR"


class EmbeddingGenerationError(AppError):
    status_code = 500
    taxonomy_category = "tool"
    error_code = "EMBEDDING_GENERATION_ERROR"


class VectorStoreNotFoundError(AppError):
    status_code = 404
    taxonomy_category = "retriever"
    error_code = "VECTOR_STORE_NOT_FOUND"


class CorruptedVectorStoreError(AppError):
    status_code = 422
    taxonomy_category = "retriever"
    error_code = "CORRUPTED_VECTOR_STORE"


class EmbeddingDimensionMismatchError(AppError):
    status_code = 400
    taxonomy_category = "retriever"
    error_code = "EMBEDDING_DIMENSION_MISMATCH"


class MetadataSyncError(AppError):
    status_code = 500
    taxonomy_category = "retriever"
    error_code = "METADATA_SYNC_ERROR"


class LLMConfigurationError(AppError):
    status_code = 500
    taxonomy_category = "deployment"
    error_code = "LLM_CONFIGURATION_ERROR"


class LLMAPIError(AppError):
    status_code = 502
    taxonomy_category = "tool"
    error_code = "LLM_API_ERROR"


class LLMTimeoutError(AppError):
    status_code = 504
    taxonomy_category = "tool"
    error_code = "LLM_TIMEOUT"


class LLMEmptyResponseError(AppError):
    status_code = 502
    taxonomy_category = "output"
    error_code = "LLM_EMPTY_RESPONSE"


class WebSearchError(AppError):
    status_code = 502
    taxonomy_category = "tool"
    error_code = "WEB_SEARCH_ERROR"


class RerankingError(AppError):
    status_code = 500
    taxonomy_category = "tool"
    error_code = "RERANKING_ERROR"


class VisionServiceError(AppError):
    status_code = 502
    taxonomy_category = "tool"
    error_code = "VISION_SERVICE_ERROR"


class PromptGenerationError(AppError):
    status_code = 400
    taxonomy_category = "prompt"
    error_code = "PROMPT_GENERATION_ERROR"


class ChatServiceError(AppError):
    status_code = 500
    taxonomy_category = "reasoning"
    error_code = "CHAT_SERVICE_ERROR"
