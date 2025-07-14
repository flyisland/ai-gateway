import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Dict, List, Optional, Set

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from duo_workflow_service.token_counter.approximate_token_counter import ApproximateTokenCounter

logger = structlog.stdlib.get_logger("message_compressor")


class MessageAge(StrEnum):
    RECENT = "recent"
    MIDDLE = "middle"
    OLD = "old"


class CompressionStrategy(ABC):
    @abstractmethod
    def can_compress(self, message: BaseMessage, age: MessageAge) -> bool:
        pass

    @abstractmethod
    def compress(self, message: BaseMessage, age: MessageAge) -> BaseMessage:
        pass


class StackTraceCompressor(CompressionStrategy):
    def __init__(self):
        self.stack_trace_patterns = [
            r'Traceback \(most recent call last\):.*?(?=\n[^\s]|\Z)',
            r'at .*?\(.*?\)\n',
            r'^\s+File ".*?", line \d+.*?\n',
            r'^\s+.*?\n(?=\s+File|\s+\w+Error:|\Z)',
        ]

    def can_compress(self, message: BaseMessage, age: MessageAge) -> bool:
        return age in [MessageAge.MIDDLE, MessageAge.OLD] and self._has_stack_trace(message.content)

    def compress(self, message: BaseMessage, age: MessageAge) -> BaseMessage:
        if not isinstance(message.content, str):
            return message

        compressed_content = self._compress_stack_traces(message.content)
        message_copy = message.model_copy()
        message_copy.content = compressed_content
        return message_copy

    def _has_stack_trace(self, content: str) -> bool:
        if isinstance(content, list):
            content = '\n'.join(str(item) for item in content)
        elif not isinstance(content, str):
            content = str(content)
        return bool(re.search(r'Traceback \(most recent call last\):|at .*?\(.*?\)', content, re.MULTILINE))

    def _compress_stack_traces(self, content: str) -> str:
        lines = content.split('\n')
        result_lines = []
        in_traceback = False

        for line in lines:
            if 'Traceback (most recent call last):' in line:
                in_traceback = True
                result_lines.append('[Stack trace compressed]')
                continue
            elif in_traceback and (line.endswith('Error:') or 'Exception:' in line):
                result_lines.append(line.strip())
                in_traceback = False
                continue
            elif not in_traceback:
                result_lines.append(line)

        return '\n'.join(result_lines)


class ToolMessageCompressor(CompressionStrategy):
    def can_compress(self, message: BaseMessage, age: MessageAge) -> bool:
        return isinstance(message, ToolMessage) and age != MessageAge.RECENT

    def compress(self, message: BaseMessage, age: MessageAge) -> BaseMessage:
        if not isinstance(message, ToolMessage):
            return message

        tool_name = getattr(message, 'name', 'unknown_tool')
        content = message.content

        if age == MessageAge.OLD:
            # Heavy compression - just status
            if 'error' in content.lower() or 'failed' in content.lower():
                compressed = f"{tool_name}: Error occurred"
            else:
                compressed = f"{tool_name}: Success"
        else:
            # Medium compression - preserve key info
            if 'error' in content.lower():
                error_match = re.search(r'(error|exception|failed).*', content.lower())
                error_msg = error_match.group(0) if error_match else "Error occurred"
                compressed = f"{tool_name}: {error_msg[:100]}..."
            else:
                # Keep first and last paragraphs for successful operations
                paragraphs = re.split(r'\n\s*\n', content)
                paragraphs = [p.strip() for p in paragraphs if p.strip()]
                if len(paragraphs) > 3:
                    compressed = f"{tool_name}: {paragraphs[0]}...{paragraphs[-1]}"
                else:
                    compressed = f"{tool_name}: {content[:200]}..."

        message_copy = message.model_copy()
        message_copy.content = compressed
        return message_copy


class AIMessageCompressor(CompressionStrategy):
    def can_compress(self, message: BaseMessage, age: MessageAge) -> bool:
        return isinstance(message, AIMessage) and age != MessageAge.RECENT

    def compress(self, message: BaseMessage, age: MessageAge) -> BaseMessage:
        if not isinstance(message, AIMessage):
            return message

        content = message.content
        if not isinstance(content, str):
            return message

        # Preserve tool calls
        if hasattr(message, 'tool_calls') and message.tool_calls:
            return message

        # TODO: apply model based summarization in the future for OLD messages
        compressed = self._compress_verbose_content(content)

        message_copy = message.model_copy()
        message_copy.content = compressed
        return message_copy

    def _compress_verbose_content(self, content: str) -> str:
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        if len(paragraphs) > 3:
            compressed_paragraphs = []
            for i, paragraph in enumerate(paragraphs):
                if i < 2 or i == len(paragraphs) - 1:
                    # Keep first 2 and last paragraph, but compress code blocks
                    compressed_para = re.sub(r'```[\s\S]*?```', '[Code block]', paragraph)
                    compressed_paragraphs.append(compressed_para)
                elif i == 2:
                    compressed_paragraphs.append("[...compressed...]")
            return '\n\n'.join(compressed_paragraphs)
        else:
            # For shorter content, just compress code blocks
            return re.sub(r'```[\s\S]*?```', '[Code block]', content)


class MessageCompressor:
    def __init__(self, token_counter: ApproximateTokenCounter):
        self.token_counter = token_counter
        self.strategies: List[CompressionStrategy] = [
            StackTraceCompressor(),
            ToolMessageCompressor(),
            AIMessageCompressor(),
        ]

        self.recent_message_count = 5
        self.landmark_keywords = {
            'system', 'error', 'failed', 'exception', 'critical',
            'plan', 'goal', 'task', 'completed', 'summary'
        }

        # Message metadata for incremental compression
        self.message_ages: Dict[int, MessageAge] = {}
        self.message_timestamps: Dict[int, datetime] = {}
        self.compressed_messages: Dict[int, BaseMessage] = {}

    def compress_messages(
        self,
        messages: List[BaseMessage],
        target_token_count: Optional[int] = None
    ) -> List[BaseMessage]:
        if not messages:
            return messages

        self._update_message_ages(messages)
        landmarks = self._identify_landmarks(messages)

        compressed = []
        current_tokens = 0

        for i, message in enumerate(messages):
            # Always preserve landmarks and recent messages
            if i in landmarks or i >= len(messages) - self.recent_message_count:
                compressed_msg = message
            else:
                # Apply incremental compression
                compressed_msg = self._apply_compression(message, i)

            compressed.append(compressed_msg)

            if target_token_count:
                current_tokens += self.token_counter.count_tokens([compressed_msg])
                if current_tokens > target_token_count:
                    return self._aggressive_compression(compressed, target_token_count)

        return compressed

    def _update_message_ages(self, messages: List[BaseMessage]) -> None:
        total_messages = len(messages)

        for i, message in enumerate(messages):
            if i >= total_messages - self.recent_message_count:
                age = MessageAge.RECENT
            elif i < total_messages // 3:
                age = MessageAge.OLD
            else:
                age = MessageAge.MIDDLE

            self.message_ages[i] = age
            self.message_timestamps[i] = datetime.now()

    def _identify_landmarks(self, messages: List[BaseMessage]) -> Set[int]:
        landmarks = set()

        for i, message in enumerate(messages):
            content = str(message.content).lower()

            # System messages are always landmarks
            if isinstance(message, SystemMessage):
                landmarks.add(i)
                continue

            # Messages with landmark keywords
            if any(keyword in content for keyword in self.landmark_keywords):
                landmarks.add(i)
                continue

            # Messages with tool calls (important for conversation flow)
            if isinstance(message, AIMessage) and hasattr(message, 'tool_calls') and message.tool_calls:
                landmarks.add(i)

        return landmarks

    def _apply_compression(self, message: BaseMessage, message_index: int) -> BaseMessage:
        # Check if we already have a compressed version
        if message_index in self.compressed_messages:
            return self.compressed_messages[message_index]

        age = self.message_ages.get(message_index, MessageAge.RECENT)
        compressed_message = message

        for strategy in self.strategies:
            if strategy.can_compress(compressed_message, age):
                compressed_message = strategy.compress(compressed_message, age)

        # Cache the compressed version
        self.compressed_messages[message_index] = compressed_message
        return compressed_message

    def _aggressive_compression(
        self,
        messages: List[BaseMessage],
        target_token_count: int
    ) -> List[BaseMessage]:
        result = []
        current_tokens = 0

        # Always keep system messages and last few messages
        system_msgs = [msg for msg in messages if isinstance(msg, SystemMessage)]
        recent_msgs = messages[-self.recent_message_count:]

        for msg in system_msgs + recent_msgs:
            result.append(msg)
            current_tokens += self.token_counter.count_tokens([msg])

        # Add compressed middle messages if we have token budget
        middle_msgs = messages[len(system_msgs):-self.recent_message_count]
        for msg in reversed(middle_msgs):  # Add most recent first
            msg_tokens = self.token_counter.count_tokens([msg])
            if current_tokens + msg_tokens <= target_token_count:
                # Apply heavy compression
                compressed = self._heavy_compress_message(msg)
                result.insert(-self.recent_message_count, compressed)
                current_tokens += self.token_counter.count_tokens([compressed])
            else:
                break

        return result

    def _heavy_compress_message(self, message: BaseMessage) -> BaseMessage:
        if isinstance(message, ToolMessage):
            tool_name = getattr(message, 'name', 'tool')
            if 'error' in str(message.content).lower():
                content = f"{tool_name} failed"
            else:
                content = f"{tool_name} succeeded"
        elif isinstance(message, AIMessage):
            content = "AI response [compressed]"
        elif isinstance(message, HumanMessage):
            content = str(message.content)[:100] + "..." if len(str(message.content)) > 100 else str(message.content)
        else:
            content = str(message.content)[:50] + "..."

        message_copy = message.model_copy()
        message_copy.content = content
        return message_copy


    def add_model_summarization_strategy(self, strategy: CompressionStrategy) -> None:
        """
        TODO: Create ModelSummarizerStrategy class that:
        - Implements CompressionStrategy interface
        - Uses small model (Claude Haiku) to summarize message content
        - Preserves key context, decisions, and conversation flow
        - Applied to MessageAge.MIDDLE and MessageAge.OLD messages
        - Maintains tool call relationships and error information
        """
        self.strategies.append(strategy)

    def _split_by_paragraphs(self, text: str) -> List[str]:
        if not isinstance(text, str):
            return [str(text)]

        # Don't split JSON or other structured data
        if text.strip().startswith(('{', '[', '<')):
            return [text]

        # Preserve code blocks by temporarily replacing them with placeholders
        code_blocks = []

        def preserve_code_block(match):
            code_blocks.append(match.group(0))
            return f"__CODE_BLOCK_{len(code_blocks)-1}__"

        # Replace code blocks with placeholders
        text_with_placeholders = re.sub(r'```[\s\S]*?```', preserve_code_block, text)

        # Split on double newlines (paragraph breaks)
        paragraphs = re.split(r'\n\s*\n', text_with_placeholders)

        # Restore code blocks and clean up
        result = []
        for paragraph in paragraphs:
            if paragraph.strip():
                # Restore any code blocks in this paragraph
                for i, code_block in enumerate(code_blocks):
                    paragraph = paragraph.replace(f"__CODE_BLOCK_{i}__", code_block)
                result.append(paragraph.strip())

        return result
