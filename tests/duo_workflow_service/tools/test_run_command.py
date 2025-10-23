from typing import List
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest

from contract import contract_pb2
from duo_workflow_service.tools.command import RunCommand, RunCommandInput


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "args", "expected_action_args"),
    [
        (
            "poetry",
            " run uvicorn  main:app --host 0.0.0.0 --port 8018 ",
            ["run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8018"],
        ),
        (
            "pytest",
            "  tests/test_main.py::test_app_start ",
            ["tests/test_main.py::test_app_start"],
        ),
        (
            "echo",
            "'hello world' test",
            ["hello world", "test"],
        ),
        (
            "cp",
            '"file with spaces.txt" destination.txt',
            ["file with spaces.txt", "destination.txt"],
        ),
    ],
)
async def test_run_command_success(
    program: str, args: str, expected_action_args: List[str], mock_success_client_event
):
    mock_outbox = MagicMock()
    mock_outbox.put_action_and_wait_for_response = AsyncMock(
        return_value=mock_success_client_event
    )

    metadata = {"outbox": mock_outbox}

    run_command = RunCommand(name="run_command", description="Run a shell command")
    run_command.metadata = metadata

    response = await run_command._arun(program=program, args=args)

    assert response == "done"

    mock_outbox.put_action_and_wait_for_response.assert_called_once()
    action = mock_outbox.put_action_and_wait_for_response.call_args[0][0]
    assert action.runCommand.program == program
    assert action.runCommand.arguments == expected_action_args
    assert action.runCommand.flags == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "args", "expected_sh_command"),
    [
        (
            "ls",
            "-l > output.txt",
            "ls -l > output.txt",
        ),
        (
            "cat",
            "file.txt | grep error",
            "cat file.txt | grep error",
        ),
        (
            "echo",
            "hello >> log.txt",
            "echo hello >> log.txt",
        ),
        (
            "python",
            "script.py 2> errors.log",
            "python script.py 2> errors.log",
        ),
        (
            "ls",
            "-l ; echo done",
            "ls -l ; echo done",
        ),
        (
            "cat",
            "< input.txt",
            "cat < input.txt",
        ),
    ],
)
async def test_run_command_with_shell_operators(
    program: str, args: str, expected_sh_command: str, mock_success_client_event
):
    """Test that commands with shell operators are wrapped in 'sh -c'."""
    mock_outbox = MagicMock()
    mock_outbox.put_action_and_wait_for_response = AsyncMock(
        return_value=mock_success_client_event
    )

    metadata = {"outbox": mock_outbox}

    run_command = RunCommand(name="run_command", description="Run a shell command")
    run_command.metadata = metadata

    response = await run_command._arun(program=program, args=args)

    assert response == "done"

    mock_outbox.put_action_and_wait_for_response.assert_called_once()
    action = mock_outbox.put_action_and_wait_for_response.call_args[0][0]
    assert action.runCommand.program == "sh"
    assert action.runCommand.arguments == ["-c", expected_sh_command]
    assert action.runCommand.flags == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "args"),
    [
        # Filenames that contain operator-like characters should NOT trigger shell mode
        ("touch", "report>summary.txt"),
        ("cat", "data<backup.txt"),
        ("rm", "arrow->file.txt"),
        # Operators without surrounding whitespace in the middle of args
        ("echo", "value>100"),
        ("grep", "a<b"),
    ],
)
async def test_run_command_no_false_positive_shell_detection(
    program: str, args: str, mock_success_client_event
):
    """Test that filenames with operator-like characters don't incorrectly trigger shell mode."""
    mock_outbox = MagicMock()
    mock_outbox.put_action_and_wait_for_response = AsyncMock(
        return_value=mock_success_client_event
    )

    metadata = {"outbox": mock_outbox}

    run_command = RunCommand(name="run_command", description="Run a shell command")
    run_command.metadata = metadata

    response = await run_command._arun(program=program, args=args)

    assert response == "done"

    mock_outbox.put_action_and_wait_for_response.assert_called_once()
    action = mock_outbox.put_action_and_wait_for_response.call_args[0][0]
    # Should use direct execution, not shell
    assert action.runCommand.program == program
    assert action.runCommand.program != "sh"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "args"),
    [
        ("echo", "'unclosed quote"),
        ("cat", 'file "with unclosed'),
        ("ls", "arg1 'another unclosed"),
    ],
)
async def test_run_command_malformed_arguments(program: str, args: str):
    """Test that malformed arguments (unclosed quotes) are handled gracefully."""
    run_command = RunCommand(name="run_command", description="Run a shell command")

    response = await run_command._arun(program=program, args=args)

    # Should return an error message instead of crashing
    assert "Invalid command arguments" in response
    assert "unclosed" in response.lower() or "malformed" in response.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "program",
    [
        "git",
        "git status",
        "git commit",
    ],
)
@mock.patch("duo_workflow_service.tools.command._execute_action")
async def test_run_disallowed_command(execute_action_mock, program):
    run_command = RunCommand(name="run_command", description="Run a shell command")

    response = await run_command._arun(program=program, args="")

    execute_action_mock.assert_not_called()
    assert "git" in response
    assert "not supported" in response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "args"),
    [
        ("ls", "&& echo done"),
        ("echo", "1 || echo failed"),
        ("test", "-f file.txt && echo exists"),
        ("command", "arg1 || backup_command"),
    ],
)
@mock.patch("duo_workflow_service.tools.command._execute_action")
async def test_run_disallowed_operators(execute_action_mock, program, args):
    """Test that && and || operators are still disallowed."""
    run_command = RunCommand(name="run_command", description="Run a shell command")

    response = await run_command._arun(program=program, args=args)

    execute_action_mock.assert_not_called()
    assert "not supported" in response
    assert any(op in response for op in ["&&", "||"])


def test_run_command_format_display_message():
    tool = RunCommand(description="Run a shell command")

    input_data = RunCommandInput(program="ls", args="-l -a /home ")

    message = tool.format_display_message(input_data)

    expected_message = "Run command: ls -l -a /home"
    assert message == expected_message
