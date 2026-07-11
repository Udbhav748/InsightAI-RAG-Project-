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
