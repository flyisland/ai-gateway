import os

HEADER_TEXT = """# Dependencies for Duo Workflow Service. Extended tests are run when these change patterns are matched.
# Note: Do not modify this file manually. Instead, run: make duo-workflow-service-dependencies
.duo-workflow-service-dependencies:
  changes:
    - duo_workflow_service/**/*
    - tests/duo_workflow_service/**/*
    - contract/**/*
    - pyproject.toml
"""

OUTPUT_FILE_PATH = ".gitlab/ci/dws-dependencies.yml"


def main():
    target_directory = "duo_workflow_service/"

    # Get lines that reference ai_gateway
    matching_lines = set()
    for root, _, filenames in os.walk(target_directory):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            if full_path.endswith(".py"):
                with open(full_path, "r") as file_contents:
                    for _, line in enumerate(file_contents):
                        if "ai_gateway" in line:
                            matching_lines.add(line.strip())

    # Add any import statements to the list of change patterns
    change_patterns = set()
    for line in matching_lines:
        splits = line.split()
        if splits[0] in ["import", "from"]:
            change_patterns.add(convert_to_path(splits[1]))
        else:
            raise Exception(  # pylint: disable=broad-exception-raised)
                f"Error, invalid import format: {line}"
            )

    change_patterns = sorted(change_patterns)
    with open(OUTPUT_FILE_PATH, "w") as output_file:
        output_file.write(HEADER_TEXT)
        for pattern in change_patterns:
            output_file.write(f"    - {pattern}\n")


def convert_to_path(module_path):
    module_path = module_path.replace(".", "/")
    if os.path.isdir(module_path):
        return module_path + "/*.py"

    if os.path.exists(module_path + ".py"):
        return module_path + ".py"

    raise Exception(  # pylint: disable=broad-exception-raised)
        f"Error, invalid module path: {module_path}"
    )


if __name__ == "__main__":
    main()
