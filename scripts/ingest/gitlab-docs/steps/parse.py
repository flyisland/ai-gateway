#!/usr/bin/env python

import glob
import os

# pylint: disable=direct-environment-variable-reference
DOC_DIR = os.getenv("GITLAB_DOCS_CLONE_DIR", "")
ROOT_URL = os.getenv("GITLAB_DOCS_WEB_ROOT_URL", "")

print(f"clone dir: {DOC_DIR}")

METADATA_KEYS = "title md5sum source source_type source_url".split()


def parse(filenames):
    for filename in filenames:
        source = filename.replace(f"{DOC_DIR}/doc/", "", 1)

        print(f"parsing: {{ filename: {filename}, source: {source} }}")

    return []


# pylint: disable=pointless-string-statement
"""
require 'json'
require_relative "base_content_parser"
require_relative "docs_content_parser"

def parse(filenames)
  filenames.map do |filename|
    source = filename.sub("#{DOC_DIR}/doc/", '')

    puts "parsing: { filename: #{filename}, source: #{source} }"

    parser = ::Gitlab::Llm::Embeddings::Utils::BaseContentParser.new( ROOT_URL )
    parser.parse_and_split(
      File.read(filename),
      source
    )
  end
end


def export(entries)
  log_name = ENV.fetch('GITLAB_DOCS_JSONL_EXPORT_PATH')
  File.delete(log_name) if File.exist?(log_name)
  File.open(log_name, 'w') do |f|
    entries.flatten.each do |entry|
      entry = entry.dup
      entry[:metadata] = entry[:metadata].slice(*METADATA_KEYS)
      f.puts JSON.dump(entry)
    end
  end
end
"""


def export(entries):
    return []


# pylint: disable=invalid-name
if __name__ == "__main__":
    mdfiles = sorted(glob.glob(f"{DOC_DIR}/doc/**/*.md", recursive=True))
    entries = parse(mdfiles)
    export(entries)
