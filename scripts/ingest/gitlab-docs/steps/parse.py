#!/usr/bin/env python

import glob
import os
import re

# pylint: disable=direct-environment-variable-reference
DOC_DIR = os.getenv("GITLAB_DOCS_CLONE_DIR", "")
ROOT_URL = os.getenv("GITLAB_DOCS_WEB_ROOT_URL", "")

print(f"clone dir: {DOC_DIR}")

FRONT_RE = re.compile(r"---\n(?P<frontmatter>.*?)---\n", re.DOTALL)
METADATA_KEYS = "title md5sum source source_type source_url".split()


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
        # source: user/application_security/dast/checks/798.38.md
        # url: https://docs.gitlab.com/ee/user/application_security/dast/browser/checks/798.38    for filename in filenames:
        source = filename.replace(f"{DOC_DIR}/doc/", "", 1)
        url = ROOT_URL + "/" + filename.replace('.md', '')

        print(f"parsing: {filename}")

        content, front = split_md(open(filename).read())

        print(content[:20])
        print(front[:10])

    #return parse(filename, source, url)


# pylint: disable=pointless-string-statement
"""
def parse(filenames)
  filenames.map do |filename|
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
