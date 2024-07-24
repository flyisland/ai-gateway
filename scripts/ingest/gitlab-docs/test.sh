#!/usr/bin/env bash

set -eu

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
STEPS_DIR="${SCRIPT_DIR}/steps"
echo "SCRIPT_DIR: ${SCRIPT_DIR}"

TEST_TAG=v17.0.1-ee
TEST_FILE=docs-${TEST_TAG}.sha256
TEST_CLONE=/tmp/gitlab-docs-${TEST_TAG}

GITLAB_DOCS_CLONE_DIR=${TEST_CLONE}
GITLAB_DOCS_JSONL_EXPORT_PATH=${TEST_CLONE}/docs-${TEST_TAG}.jsonl

echo "------------------------------------------------------- Clone Docs -------------------------------------------------------"
rm -Rf "${GITLAB_DOCS_CLONE_DIR}" 
git clone --branch "${TEST_TAG}" --depth 1 "${GITLAB_DOCS_REPO}" "${GITLAB_DOCS_CLONE_DIR}"

echo "------------------------------------------------------- Validating -------------------------------------------------------"
"${STEPS_DIR}"/validate.sh
echo "------------------------------------------------------- Exporting Variables -------------------------------------------------------"
source "${STEPS_DIR}"/export_variables.sh
echo "------------------------------------------------------- Parsing -------------------------------------------------------"
echo "***** Ruby parser to $GITLAB_DOCS_JSONL_EXPORT_PATH *****"
"${STEPS_DIR}"/parse.rb
echo
JSONL_PYTHON="$PWD/docs-python.jsonl"
echo "***** Python parser to $JSONL_PYTHON *****"
GITLAB_DOCS_JSONL_EXPORT_PATH="$JSONL_PYTHON" "$STEPS_DIR"/parse.py

echo "------------------------------------------------------- Comparing Results -------------------------------------------------------"
echo "Validate checksum of generated ${GITLAB_DOCS_JSONL_EXPORT_PATH}..."
cp "${SCRIPT_DIR}/testdata/${TEST_FILE}" "${TEST_CLONE}/"
cd ${TEST_CLONE}
sha256sum -c ${TEST_FILE}
cd -

echo "Count chunked files..."
echo "ruby: $(jq .metadata.source < "${GITLAB_DOCS_JSONL_EXPORT_PATH}" | uniq | wc -l)"
echo "python: $(jq .metadata.source < "${JSONL_PYTHON}" | uniq | wc -l)"
