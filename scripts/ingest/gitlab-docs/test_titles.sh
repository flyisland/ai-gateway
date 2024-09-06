#!/bin/bash

set -eu

FIRST=/tmp/ruby.jsonl
SECOND=/tmp/python.jsonl

echo "--- Extracting titles grouped under filename"

jq --slurp 'group_by(.metadata.source) | map({source: .[0].metadata.source, titles: [map(.metadata.title)]})' < "$FIRST" > "$FIRST.titles"

jq --slurp 'group_by(.metadata.source) | map({source: .[0].metadata.source, titles: [map(.metadata.title)]})' < "$SECOND" > "$SECOND.titles"

diff -u3 "$FIRST.titles" "$SECOND.titles"
