#!/usr/bin/env python

import dataclasses
import json
import os
import re
from hashlib import sha256
from pathlib import Path

# pylint: disable=direct-environment-variable-reference
DOC_DIR = os.getenv("GITLAB_DOCS_CLONE_DIR", "")
ROOT_URL = os.getenv("GITLAB_DOCS_WEB_ROOT_URL", "https://gitlab.com/help")
LOG_PATH = os.getenv("GITLAB_DOCS_JSONL_EXPORT_PATH", "docs.jsonl")

print(f"clone dir: {DOC_DIR}")
print(f"root url:  {ROOT_URL}")

FRONT_RE = re.compile(r"---\n(?P<frontmatter>.*?)---\n", re.DOTALL)
TITLE_RE = re.compile(r"(\s*<!--.+?-->\s*)?#+\s+(?P<title>.+?)\n", re.DOTALL)

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


def warn(s):
    """Print s to stderr in red"""
    red = "\033[31m"
    reset = "\033[0m"
    print(f"{red}--- WARNING: {s}{reset}")


def batched(s, n):
    """Yield chunks of len n from s

    batched('ABCDEFG', 3) → ABC DEF G
    """
    for i in range(0, len(s), n):
        yield s[i : i + n]


def batched_lines(s, n):
    """Yield chunks of lines, with chunk len no more than n"""
    chunk = ""
    for line in s.splitlines(keepends=True):
        if len(chunk + line) > n:
            # XXX: Ruby parser only strips one newline
            yield chunk.removesuffix("\n")
            chunk = line
        else:
            chunk += line
    if len(chunk) <= n:
        yield chunk


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
        # XXX: previous Ruby code strips tails that are less than < MIN_CHARS_PER_EMBEDDING
        # but it is not clear why, so...
        #
        # warn until there is an answer to
        # https://gitlab.com/gitlab-org/modelops/applied-ml/code-suggestions/ai-assist/-/issues/562
        warn(
            f"{filename}\n"
            + f"removed from dataset, filesize {len(filename)} is less that MIN_CHARS_PER_EMBEDDING ({MIN_CHARS_PER_EMBEDDING})\n\n"
            + content
            + "----------------------------------------"
        )
    else:
        # chunks = batched(content, MAX_CHARS_PER_EMBEDDING)
        chunks = batched_lines(content.strip(), MAX_CHARS_PER_EMBEDDING)
        for c in chunks:
            if len(c) < MIN_CHARS_PER_EMBEDDING:
                return
            yield c


def parse(filenames):
    """Generate RAGChunk entries"""
    for filename in filenames:
        # filename: /tmp/gitlab-docs-v17.0.1-ee/doc/user/application_security/dast/checks/798.38.md
        print(f"parsing: {filename}")

        metadata = Metadata()
        # source: user/application_security/dast/checks/798.38.md
        metadata.source = str(filename).replace(f"{DOC_DIR}/doc/", "", 1)
        # source_url: https://docs.gitlab.com/ee/user/application_security/dast/browser/checks/798.38
        metadata.source_url = ROOT_URL + "/" + metadata.source.removesuffix(".md")

        with open(filename, "r", encoding="utf-8") as file:
            text = file.read()
        # XXX: should this field be renamed to .checksum ?
        metadata.md5sum = sha256(text.encode("utf-8")).hexdigest()
        content, _ = split_md(text)

        match = TITLE_RE.match(content.lstrip())
        if match:
            metadata.title = match.group("title")

        for chunk in split_to_chunks(content, metadata.source):
            yield RAGChunk(chunk, metadata)


def export(entries):
    """Save chunks to JSONL"""
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)
    with open(LOG_PATH, "w", encoding="utf-8") as fw:
        for entry in entries:
            fw.write(json.dumps(dataclasses.asdict(entry)))
            fw.write("\n")


if __name__ == "__main__":
    mdfiles = sorted(Path(DOC_DIR).glob("doc/**/*.md"))
    entries = parse(mdfiles)
    export(entries)
