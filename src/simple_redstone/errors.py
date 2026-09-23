class SimpleRedstoneError(Exception):
    """Base exception for Simple Redstone errors."""


class ParseError(SimpleRedstoneError):
    """An error encountered while parsing Simple Redstone input."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "<string>",
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.source = source
        self.line = line
        self.column = column

    def __str__(self) -> str:
        location = self.source
        if self.line is not None:
            location += f":{self.line}"
            if self.column is not None:
                location += f":{self.column}"
        return f"{location}: {self.message}"


class BlockExpansionError(SimpleRedstoneError):
    """A malformed or unsupported block expression."""


class LayoutError(SimpleRedstoneError):
    """Raised when block layout or ground generation cannot be completed."""


class BackendError(SimpleRedstoneError):
    """Raised when a structure cannot be written to an output format."""


class RenderError(SimpleRedstoneError):
    """Raised when a structure cannot be rendered."""
