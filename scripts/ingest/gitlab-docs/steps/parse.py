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
LOG_PATH = os.getenv("GITLAB_DOCS_JSONL_EXPORT_PATH", "docs.jsonl")

print(f"clone dir: {DOC_DIR}")

FRONT_RE = re.compile(r"---\n(?P<frontmatter>.*?)---\n", re.DOTALL)
TITLE_RE = re.compile(r"#+\s+(?P<title>.+)\n")

MIN_CHARS_PER_EMBEDDING = 100
MAX_CHARS_PER_EMBEDDING = 1500


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


def split_to_chunks(content, filename):
    """Get chunks of content if its larger than embedding min chars"""
    if len(content) < MIN_CHARS_PER_EMBEDDING:
        # warn until there is an answer
        # https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/-/issues/562
        print(f"--- WARNING: {filename}")
        print(
            f"removed from dataset, filesize {len(filename)} is less that MIN_CHARS_PER_EMBEDDING ({MIN_CHARS_PER_EMBEDDING})"
        )
        print(content)
        print("----------------------------------------")


def parse(filenames):
    """Generate RAGChunk entries"""
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
        content, _ = split_md(text)

        match = TITLE_RE.match(content.lstrip())
        if match:
            metadata.title = match.group("title")

        split_to_chunks(content, metadata.source)

        yield RAGChunk("", metadata)


def export(entries):
    """Save chunks to JSONL"""
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    with open(LOG_PATH, "w", encoding="utf-8") as fw:
        for entry in entries:
            fw.write(json.dumps(dataclasses.asdict(entry)))
            fw.write("\n")


if __name__ == "__main__":
    mdfiles = sorted(glob.glob(f"{DOC_DIR}/doc/**/*.md", recursive=True))
    entries = parse(mdfiles)
    export(entries)
