"""Domain-specific exceptions, mapped to HTTP responses in app.core.error_handlers."""


class AppError(Exception):
    status_code: int = 500

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class UnsupportedFileTypeError(AppError):
    status_code = 415


class EmptyFileError(AppError):
    status_code = 400


class FileTooLargeError(AppError):
    status_code = 413


class DocumentNotFoundError(AppError):
    status_code = 404


class CorruptedPDFError(AppError):
    status_code = 422


class TextExtractionError(AppError):
    status_code = 500


class EmbeddingModelLoadError(AppError):
    status_code = 500


class EmbeddingGenerationError(AppError):
    status_code = 500


class VectorStoreNotFoundError(AppError):
    status_code = 404


class CorruptedVectorStoreError(AppError):
    status_code = 422


class EmbeddingDimensionMismatchError(AppError):
    status_code = 400


class MetadataSyncError(AppError):
    status_code = 500


class LLMConfigurationError(AppError):
    status_code = 500


class LLMAPIError(AppError):
    status_code = 502


class LLMTimeoutError(AppError):
    status_code = 504


class LLMEmptyResponseError(AppError):
    status_code = 502


class PromptGenerationError(AppError):
    status_code = 400


class ChatServiceError(AppError):
    status_code = 500
