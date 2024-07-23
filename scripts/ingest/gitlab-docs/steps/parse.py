#!/usr/bin/env python

import dataclasses
import glob
import json
import os
import re
from hashlib import sha256

# pylint: disable=direct-environment-variable-reference
DOC_DIR = os.getenv("GITLAB_DOCS_CLONE_DIR", "")
ROOT_URL = os.getenv("GITLAB_DOCS_WEB_ROOT_URL", "")

print(f"clone dir: {DOC_DIR}")

FRONT_RE = re.compile(r"---\n(?P<frontmatter>.*?)---\n", re.DOTALL)
METADATA_KEYS = "title md5sum source source_type source_url".split()


@dataclasses.dataclass
class Metadata:
    title: str = ""
    md5sum: str = ""
    source: str = ""
    source_type: str = "doc"
    source_url: str = ""


@dataclasses.dataclass
class RAGChunk:
    content: str
    metadata: Metadata


def split_md(markdown):
    """Separates front matter from markdown content and returns pair
    of strings (content, frontmatter)"""
    match = FRONT_RE.match(markdown)
    if not match:
        return markdown, ""
    _, end = match.span()
    return markdown[end:], match.group("frontmatter")


def parse(filenames):
    for filename in filenames:
        # filename: /tmp/gitlab-docs-v17.0.1-ee/doc/user/application_security/dast/checks/798.38.md
        print(f"parsing: {filename}")

        metadata = Metadata()
        # source: user/application_security/dast/checks/798.38.md
        metadata.source = filename.replace(f"{DOC_DIR}/doc/", "", 1)
        # source_url: https://docs.gitlab.com/ee/user/application_security/dast/browser/checks/798.38
        metadata.source_url = ROOT_URL + "/" + filename.replace(".md", "")

        with open(filename, "r", encoding="utf-8") as file:
            text = file.read()
        # TODO: should this field be renamed to .checksum ?
        metadata.md5sum = sha256(text.encode("utf-8")).hexdigest()
        content, front = split_md(text)

        yield metadata


# pylint: disable=pointless-string-statement
"""
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
    for entry in entries:
        print(json.dumps(dataclasses.asdict(entry)))


# pylint: disable=invalid-name
if __name__ == "__main__":
    mdfiles = sorted(glob.glob(f"{DOC_DIR}/doc/**/*.md", recursive=True))
    entries = parse(mdfiles)
    export(entries)
