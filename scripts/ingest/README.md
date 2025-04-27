### Chunk GitLab documentation into JSON for RAG

Ingest scripts clone GitLab source to get GitLab documentations,
then read doc .md files and chunk them into single JSON file.

### Running

First, build Docker image with the sources and dependencies
(example for `podman`). From the current dir, run:

```shell
podman build ../.. -f Dockerfile -t gitlab-ingest
```

Building the image will take a while..


