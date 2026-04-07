class FaultAtlasError(Exception):
    """Base error for API orchestration failures."""


class LLMBackendUnavailableError(FaultAtlasError):
    def __init__(self, backend: str, message: str) -> None:
        super().__init__(message)
        self.backend = backend


class LLMEmptyResponseError(FaultAtlasError):
    pass


class LLMOutputParseError(FaultAtlasError):
    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output
