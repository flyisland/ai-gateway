### Chunk GitLab documentation into JSON for RAG

Ingest scripts clone GitLab source to get GitLab documentations,
then read doc .md files and chunk them into single JSON file. As
the last step, chunks are uploaded in to Google Cloud BigTable.

### Running

First, build Docker image with the sources and dependencies
(example for `podman`). From the current dir, run:

```shell
podman build ../.. -f Dockerfile -t gitlab-ingest
```

Building the image takes a while..

Running requires setting a bunch of environment variables, most
notably Google Cloud credentials. Set them using .env file (see
`testparse.env` for an example). Create `localdev.env` and run:

```shell
podman run -it --rm --env-file localdev.env gitlab-ingest
```

### Testing markdown parsers only

To test parse process without Google Cloud access, execute
`test_parse.sh` script with provided `testparse.env`:

```shell
podman run -it --rm --env-file testparse.env gitlab-ingest scripts/ingest/gitlab-docs/test_parse.sh
```

