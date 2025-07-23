from abc import ABC
from enum import StrEnum
from functools import cached_property
from typing import Any, Callable, NamedTuple, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, PrivateAttr

from duo_workflow_service.agent_platform.experimental.state import FlowStateKeys
from duo_workflow_service.entities import UiChatLog

__all__ = [
    "BaseUILogEvents",
    "BaseUILogWriter",
    "UIHistory",
]


class BaseUILogEvents(StrEnum):
    """Base class for UI log event enumerations.

    This class provides a base for defining event enumerations for UI logging.
    It enforces naming conventions for enum values and keys.

    Enum values must:
    - Start with 'on_' prefix
    - Have keys that are uppercase versions of the values

    Example:
        class MyUIEvents(BaseUILogEvents):
            ON_START = "on_start"  # Correct naming
            ON_END = "on_end"      # Correct naming

            # The following would raise errors:
            # START = "start"      # Missing 'on_' prefix
            # Start = "on_start"   # Key not uppercase version of value
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for member in cls:
            if not member.value.startswith("on_"):
                raise ValueError(
                    f"All enum values must start with 'on_', but got: {member.value}"
                )

            # Validate that key is uppercase version of value
            expected_key = member.value.upper()
            if member.name != expected_key:
                raise ValueError(
                    f"Enum key '{member.name}' should be '{expected_key}' "
                    f"(uppercase of value '{member.value}')"
                )

    @staticmethod
    def _generate_next_value_(
        name: str, start: int, count: int, last_values: list[str]
    ) -> str:
        return name.lower()


class _UILogEntry(NamedTuple):
    record: UiChatLog
    event: BaseUILogEvents


class _UILogCallback(Protocol):
    def __call__(self, log_entry: _UILogEntry) -> None: ...


class BaseUILogWriter[E: BaseUILogEvents](ABC):
    """Abstract base class for UI log writers.

    Provides a base implementation for writing UI logs with different log levels.
    Subclasses must implement the events_type property and appropriate _create_*_log methods
    for each supported log level.

    By default, the supported log levels are 'success', 'error', and 'warning'.

    Args:
        log_callback: A callback function that will be called with each log entry
        levels: Optional sequence of log level names to support. Defaults to ["success", "error", "warning"]

    Example:
        class MyEvents(BaseUILogEvents):
            ON_START = "on_start"
            ON_END = "on_end"

        class MyWriter(BaseUILogWriter[MyEvents]):
            @property
            def events_type(self) -> type[MyEvents]:
                return MyEvents

            def _create_success_log(self, message: str, **kwargs) -> UiChatLog:
                return UiChatLog(
                    message_type="text",
                    content=message,
                    timestamp="2023-01-01T12:00:00"
                )

            def _create_error_log(self, message: str, **kwargs) -> UiChatLog:
                return UiChatLog(
                    message_type="error",
                    content=f"ERROR: {message}",
                    timestamp="2023-01-01T12:00:00"
                )

        # Create a writer with a callback
        def log_callback(entry: _UILogEntry) -> None:
            print(f"Logged: {entry.record.content}")

        writer = MyWriter(log_callback, levels=["success", "error"])

        # Log messages with different levels
        writer.success("Operation successful", event=MyEvents.ON_END)
        writer.error("Operation failed", event=MyEvents.ON_END)

        # The following will raise an error as the `warning` logging is not implemented
        writer.warning("Proceeding with caution", event=MyEvents.ON_START)
    """

    def __init__(
        self, log_callback: _UILogCallback, levels: Optional[Sequence[str]] = None
    ):
        self._log_callback = log_callback
        self._levels = (
            set(levels) if levels is not None else {"success", "error", "warning"}
        )

    @property
    def events_type(self) -> type[E]:
        raise NotImplementedError

    def _log(self, level: str, *args, **kwargs) -> None:
        level_log_fn_name = f"_create_{level}_log"
        level_log_fn = getattr(self, level_log_fn_name, None)

        if not callable(level_log_fn):
            raise AttributeError(
                f"{self.__class__.__name__} requires method"
                f" '{level_log_fn_name}(*args, **kwargs)' for logging level '{level}'"
            )

        event: E | None = kwargs.pop("event", None)
        if not event:
            raise ValueError(
                "Missing required keyword argument: 'event' cannot be None or empty"
            )

        if event not in self.events_type:
            raise TypeError(
                f"Expected 'event' to be an instance of {self.events_type}, got {type(event).__name__} instead"
            )

        record = level_log_fn(*args, **kwargs)
        self._log_callback(_UILogEntry(record=record, event=event))

    def __getattr__(self, level: str) -> Callable[..., None]:
        if level in self._levels:
            return lambda *args, **kwargs: self._log(level, *args, **kwargs)

        raise AttributeError(
            f"'{self.__class__.__name__}' has no log level method '{level}'"
        )


class UIHistory[W: BaseUILogWriter, E: BaseUILogEvents](BaseModel):
    """A model for tracking UI log history.

    Maintains a history of UI log entries and provides access to a log writer.
    Only logs events that are included in the events list.

    Attributes:
        writer_class: The BaseUILogWriter subclass to use for creating logs
        events: A list of event enum values to include in the history

    Example:
        class MyEvents(BaseUILogEvents):
            ON_START = "on_start"
            ON_END = "on_end"

        class MyWriter(BaseUILogWriter[MyEvents]):
            @property
            def events_type(self) -> type[MyEvents]:
                return MyEvents

            def _create_success_log(self, message: str, **kwargs) -> UiChatLog:
                return UiChatLog(
                    message_type="text",
                    content=message,
                    timestamp="2023-01-01T12:00:00"
                )

        # Create a history tracking specific events
        history = UIHistory(writer_class=MyWriter, events=[MyEvents.ON_START])

        # Use the log writer to create logs
        history.log.success("Starting process", event=MyEvents.ON_START)

        # The following will raise an error as the ON_END event was not enabled
        history.log.success("Starting process", event=MyEvents.ON_END)

        # Access the state containing all logs
        state = history.state
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    writer_class: type[W]
    events: list[E]

    _logs: list[_UILogEntry] = PrivateAttr(default_factory=list)

    def _add_log_to_history(self, log_entry: _UILogEntry) -> None:
        """Callback function for writers."""
        if log_entry.event not in self.events:
            raise ValueError(f"Event '{log_entry.event}' is not enabled for logging.")

        self._logs.append(log_entry)

    @cached_property
    def log(self) -> W:
        return self.writer_class(self._add_log_to_history)

    @property
    def state(self) -> dict[str, Any]:
        # Log only specified events
        logs = [log.record for log in self._logs if log.event in self.events]

        return {FlowStateKeys.UI_CHAT_LOG: logs}
