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

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class UnauthorizedError(AppError):
    status_code = 401
    taxonomy_category = "input"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    taxonomy_category = "input"


class EmptyFileError(AppError):
    status_code = 400
    taxonomy_category = "input"


class FileTooLargeError(AppError):
    status_code = 413
    taxonomy_category = "input"


class DocumentNotFoundError(AppError):
    status_code = 404
    taxonomy_category = "input"


class ConfirmationRequiredError(AppError):
    status_code = 400
    taxonomy_category = "input"


class CorruptedPDFError(AppError):
    status_code = 422
    taxonomy_category = "input"


class TextExtractionError(AppError):
    status_code = 500
    taxonomy_category = "tool"


class EmbeddingModelLoadError(AppError):
    status_code = 500
    taxonomy_category = "deployment"


class EmbeddingGenerationError(AppError):
    status_code = 500
    taxonomy_category = "tool"


class VectorStoreNotFoundError(AppError):
    status_code = 404
    taxonomy_category = "retriever"


class CorruptedVectorStoreError(AppError):
    status_code = 422
    taxonomy_category = "retriever"


class EmbeddingDimensionMismatchError(AppError):
    status_code = 400
    taxonomy_category = "retriever"


class MetadataSyncError(AppError):
    status_code = 500
    taxonomy_category = "retriever"


class LLMConfigurationError(AppError):
    status_code = 500
    taxonomy_category = "deployment"


class LLMAPIError(AppError):
    status_code = 502
    taxonomy_category = "tool"


class LLMTimeoutError(AppError):
    status_code = 504
    taxonomy_category = "tool"


class LLMEmptyResponseError(AppError):
    status_code = 502
    taxonomy_category = "output"


class WebSearchError(AppError):
    status_code = 502
    taxonomy_category = "tool"


class RerankingError(AppError):
    status_code = 500
    taxonomy_category = "tool"


class VisionServiceError(AppError):
    status_code = 502
    taxonomy_category = "tool"


class PromptGenerationError(AppError):
    status_code = 400
    taxonomy_category = "prompt"


class ChatServiceError(AppError):
    status_code = 500
    taxonomy_category = "reasoning"
