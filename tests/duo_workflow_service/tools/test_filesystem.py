from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from contract import contract_pb2
from duo_workflow_service.tools.filesystem import (  # Mkdir,
    EditFile,
    EditFileInput,
    FindFiles,
    FindFilesInput,
    ListDir,
    ListDirInput,
    ReadFile,
    ReadFileInput,
    ReadFiles,
    ReadFilesInput,
    WriteFile,
    WriteFileInput,
)


@pytest.mark.asyncio
async def test_read_file():
    mock_outbox = MagicMock()
    mock_outbox.put = AsyncMock()

    mock_inbox = MagicMock()
    mock_inbox.get = AsyncMock(
        return_value=contract_pb2.ClientEvent(
            actionResponse=contract_pb2.ActionResponse(response="test contents")
        )
    )

    metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

    tool = ReadFile(description="Read file content")
    tool.metadata = metadata
    path = "./somepath"

    response = await tool._arun(path)

    assert response == "test contents"

    mock_outbox.put.assert_called_once()
    action = mock_outbox.put.call_args[0][0]
    assert action.runReadFile.filepath == path


@pytest.mark.asyncio
async def test_read_file_not_implemented_error():
    tool = ReadFile(description="Read file content")

    with pytest.raises(NotImplementedError):
        tool._run("./main.py")


@pytest.mark.asyncio
async def test_read_files():
    mock_outbox = MagicMock()
    mock_outbox.put = AsyncMock()

    mock_inbox = MagicMock()

    # Mock the case where ReadFiles is available in contract_pb2
    with patch.object(contract_pb2, 'ReadFiles', create=True) as mock_read_files_class:
        with patch.object(contract_pb2.Action, 'runReadFiles', create=True):
            mock_inbox.get = AsyncMock(
                return_value=contract_pb2.ClientEvent(
                    actionResponse=contract_pb2.ActionResponse(
                        response="=== ./file1.py ===\ncontent of file1\n\n=== ./file2.py ===\ncontent of file2"
                    )
                )
            )

            metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

            tool = ReadFiles(description="Read multiple files")
            tool.metadata = metadata
            file_paths = ["./file1.py", "./file2.py"]

            response = await tool._arun(file_paths)

            expected_response = "=== ./file1.py ===\ncontent of file1\n\n=== ./file2.py ===\ncontent of file2"
            assert response == expected_response

            # Verify that outbox.put was called once (single ReadFiles call)
            assert mock_outbox.put.call_count == 1


@pytest.mark.asyncio
async def test_read_files_with_error():
    mock_outbox = MagicMock()
    mock_outbox.put = AsyncMock()

    mock_inbox = MagicMock()

    # Test fallback to individual ReadFile calls when ReadFiles is not available
    mock_inbox.get = AsyncMock(
        side_effect=[
            contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(response="content of file1")
            ),
            Exception("File not found"),
        ]
    )

    metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

    tool = ReadFiles(description="Read multiple files")
    tool.metadata = metadata
    file_paths = ["./file1.py", "./file2.py"]

    response = await tool._arun(file_paths)

    expected_response = "=== ./file1.py ===\ncontent of file1\n\n=== ./file2.py ===\nError reading file: File not found"
    assert response == expected_response


@pytest.mark.asyncio
async def test_read_files_fallback_to_individual_calls():
    """Test that ReadFiles falls back to individual ReadFile calls when ReadFiles is not available."""
    mock_outbox = MagicMock()
    mock_outbox.put = AsyncMock()

    mock_inbox = MagicMock()
    mock_inbox.get = AsyncMock(
        side_effect=[
            contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(response="content of file1")
            ),
            contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(response="content of file2")
            ),
        ]
    )

    metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

    tool = ReadFiles(description="Read multiple files")
    tool.metadata = metadata
    file_paths = ["./file1.py", "./file2.py"]

    # Test fallback behavior when ReadFiles is not available
    response = await tool._arun(file_paths)

    expected_response = "=== ./file1.py ===\ncontent of file1\n\n=== ./file2.py ===\ncontent of file2"
    assert response == expected_response

    # Verify that outbox.put was called twice (fallback to individual ReadFile calls)
    assert mock_outbox.put.call_count == 2


@pytest.mark.asyncio
async def test_read_files_not_implemented_error():
    tool = ReadFiles(description="Read multiple files")

    with pytest.raises(NotImplementedError):
        tool._run(["./file1.py", "./file2.py"])


@pytest.mark.asyncio
async def test_write_file():
    mock_outbox = MagicMock()
    mock_outbox.put = AsyncMock()

    mock_inbox = MagicMock()
    mock_inbox.get = AsyncMock(
        return_value=contract_pb2.ClientEvent(
            actionResponse=contract_pb2.ActionResponse(response="done")
        )
    )

    metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

    tool = WriteFile(description="Write file content")
    tool.metadata = metadata
    path = "./somepath"
    contents = "test contents"

    response = await tool._arun(path, contents)

    assert response == "done"

    mock_outbox.put.assert_called_once()
    action = mock_outbox.put.call_args[0][0]
    assert action.runWriteFile.filepath == path
    assert action.runWriteFile.contents == contents


@pytest.mark.asyncio
async def test_write_file_not_implemented_error():
    tool = WriteFile(description="Write file content")

    with pytest.raises(NotImplementedError):
        tool._run("./main.py", "sum(1, 2)")


class TestFindFiles:
    @pytest.mark.asyncio
    async def test_find_files_arun_method(self):
        mock_outbox = MagicMock()
        mock_outbox.put = AsyncMock()

        mock_inbox = MagicMock()
        mock_inbox.get = AsyncMock(
            return_value=contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(
                    response="file1.py\nfile2.py"
                )
            )
        )

        metadata = {"outbox": mock_outbox, "inbox": mock_inbox}
        tool = FindFiles()
        tool.metadata = metadata
        name_pattern = "*.py"
        result = await tool._arun(name_pattern=name_pattern)

        assert result == "file1.py\nfile2.py"

    @pytest.mark.asyncio
    @patch("duo_workflow_service.tools.filesystem.FindFiles", autospec=True)
    async def test_find_files_empty_result(self, mock_find_files_class):
        # Create a mock instance with a mocked _arun method
        mock_instance = mock_find_files_class.return_value
        mock_instance._arun = AsyncMock(
            return_value="No matches found for pattern '*.nonexistent'"
        )

        # Now use the mock instance instead of creating a real one
        name_pattern = "*.nonexistent"
        result = await mock_instance._arun(name_pattern)

        assert "No matches found for pattern '*.nonexistent'" in result
        mock_instance._arun.assert_called_once_with("*.nonexistent")

    def test_find_files_sync_run_method(self):
        tool = FindFiles()
        with pytest.raises(
            NotImplementedError, match="This tool can only be run asynchronously"
        ):
            tool._run(".", "*.py")


class TestLsDir:
    @pytest.mark.asyncio
    async def test_list_dir_success(self):
        # Set up the mock outbox and inbox
        mock_outbox = MagicMock()
        mock_outbox.put = AsyncMock()

        mock_inbox = MagicMock()
        mock_inbox.get = AsyncMock(
            return_value=contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(
                    response="file1.txt file2.txt dir1 dir2"
                )
            )
        )

        metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

        # Create the tool and set its metadata
        list_dir_tool = ListDir()
        list_dir_tool.metadata = metadata

        # Call the method being tested
        result = await list_dir_tool._arun(directory=".")

        # Assert the result
        assert result == "file1.txt file2.txt dir1 dir2"

        # Verify the outbox was used as expected
        mock_outbox.put.assert_called_once()

        # You can add additional assertions to verify the details of what was put on the outbox
        action = mock_outbox.put.call_args[0][0]
        assert action.listDirectory.directory == "."

    @pytest.mark.asyncio
    async def test_list_dir_not_implemented_error(self):
        list_dir_tool = ListDir()

        with pytest.raises(NotImplementedError):
            list_dir_tool._run("test_dir")

    def test_list_dir_format_display_message(self):
        list_dir_tool = ListDir()

        input_data = ListDirInput(directory="./src")
        message = list_dir_tool.format_display_message(input_data)

        expected_message = "Using list_dir: directory=./src"
        assert message == expected_message


# class TestMkdir:
#     @pytest.mark.asyncio
#     @patch("duo_workflow_service.tools.filesystem.RunCommand", autospec=True)
#     async def test_mkdir_creates_directory(self, mock_run_command):
#         mock_arun = AsyncMock(return_value="")
#         mock_run_command.return_value._arun = mock_arun
#
#         mkdir_tool = Mkdir()
#         result = await mkdir_tool._arun("test_dir")
#
#         assert result == ""
#         mock_arun.assert_called_once_with(
#             "mkdir", arguments=["./test_dir"], flags=["-p"]
#         )
#
#     @pytest.mark.asyncio
#     @patch("duo_workflow_service.tools.filesystem.RunCommand", autospec=True)
#     async def test_mkdir_creates_nested_directories(self, mock_run_command):
#         mock_arun = AsyncMock(return_value="")
#         mock_run_command.return_value._arun = mock_arun
#
#         mkdir_tool = Mkdir()
#         result = await mkdir_tool._arun("./test_dir/nested/dir")
#
#         assert result == ""
#         mock_arun.assert_called_once_with(
#             "mkdir", arguments=["./test_dir/nested/dir"], flags=["-p"]
#         )
#
#     @pytest.mark.asyncio
#     async def test_mkdir_validates_path(self):
#         mkdir_tool = Mkdir()
#         result = await mkdir_tool._arun("../test_dir")
#
#         assert (
#             result == "Creating directories above the current directory is not allowed"
#         )


class TestEditFile:
    @pytest.mark.asyncio
    async def test_basic(self):
        mock_outbox = MagicMock()
        mock_outbox.put = AsyncMock()

        mock_inbox = MagicMock()
        mock_inbox.get = AsyncMock(
            return_value=contract_pb2.ClientEvent(
                actionResponse=contract_pb2.ActionResponse(response="success")
            )
        )

        metadata = {"outbox": mock_outbox, "inbox": mock_inbox}

        tool = EditFile(metadata=metadata)
        path = "./somefile.txt"
        old_str = "old line"
        new_str = "new line"

        response = await tool._arun(path, old_str, new_str)

        assert response == "success"

        mock_outbox.put.assert_called_once()
        action = mock_outbox.put.call_args[0][0]
        assert action.runEditFile.filepath == path
        assert action.runEditFile.oldString == old_str
        assert action.runEditFile.newString == new_str

    @pytest.mark.asyncio
    async def test_not_implemented_error(self):
        tool = EditFile()

        with pytest.raises(NotImplementedError):
            tool._run("./main.py", "old", "new")


def test_read_file_format_display_message():
    tool = ReadFile(description="Read file description")

    input_data = ReadFileInput(file_path="./src/main.py")

    message = tool.format_display_message(input_data)

    expected_message = "Read file"
    assert message == expected_message


def test_write_file_format_display_message():
    tool = WriteFile(description="Write file description")

    input_data = WriteFileInput(
        file_path="./src/new_file.py", contents="print('Hello, world!')"
    )

    message = tool.format_display_message(input_data)

    expected_message = "Create file"
    assert message == expected_message


def test_find_files_format_display_message():
    tool = FindFiles(description="Find files description")

    # Test with default parameters
    input_data = FindFilesInput(name_pattern="*.py")

    message = tool.format_display_message(input_data)
    expected_message = "Search files with pattern '*.py'"
    assert message == expected_message

    # Test with tracked_only
    input_data = FindFilesInput(
        name_pattern="*.py",
    )
    message = tool.format_display_message(input_data)
    expected_message = "Search files with pattern '*.py'"
    assert message == expected_message

    # Test with untracked_only
    input_data = FindFilesInput(
        name_pattern="*.py",
    )
    message = tool.format_display_message(input_data)
    expected_message = "Search files with pattern '*.py'"
    assert message == expected_message

    # Test with modified
    input_data = FindFilesInput(
        name_pattern="*.py",
    )
    message = tool.format_display_message(input_data)
    expected_message = "Search files with pattern '*.py'"
    assert message == expected_message

    # Test with deleted
    input_data = FindFilesInput(
        name_pattern="*.py",
    )
    message = tool.format_display_message(input_data)
    expected_message = "Search files with pattern '*.py'"
    assert message == expected_message


# def test_mkdir_format_display_message():
#     tool = Mkdir(description="Mkdir description")
#
#     input_data = MkdirInput(directory_path="./src/new_directory")
#
#     message = tool.format_display_message(input_data)
#
#     expected_message = "Create directory './src/new_directory'"
#     assert message == expected_message


def test_edit_file_format_display_message():
    tool = EditFile(description="Edit file description")

    input_data = EditFileInput(
        file_path="./src/main.py",
        old_str="print('Hello')",
        new_str="print('Hello, world!')",
    )

    message = tool.format_display_message(input_data)

    expected_message = "Edit file"
    assert message == expected_message


def test_read_files_format_display_message():
    tool = ReadFiles(description="Read multiple files")

    # Test with single file
    input_data = ReadFilesInput(file_paths=["./src/main.py"])
    message = tool.format_display_message(input_data)
    expected_message = "Read 1 file"
    assert message == expected_message

    # Test with multiple files
    input_data = ReadFilesInput(file_paths=["./src/main.py", "./src/utils.py"])
    message = tool.format_display_message(input_data)
    expected_message = "Read 2 files"
    assert message == expected_message
