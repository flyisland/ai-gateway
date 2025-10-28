# Use official Red Hat UBI9 Python 3.12 full image for FIPS compliance
# Using full image instead of minimal to have access to dnf and standard utilities like parallel
FROM registry.access.redhat.com/ubi9/python-312:latest AS base-image

USER 0

ARG FIPS=1
ARG OPENSSL_FORCE_FIPS_MODE=1
ARG OPENSSL_FIPS=1
ARG POETRY_VERSION=2.2.1
ARG GITLAB_API_KEY

ENV POETRY_VERSION=${POETRY_VERSION} \
    FIPS=${FIPS} \
    OPENSSL_FORCE_FIPS_MODE=${OPENSSL_FORCE_FIPS_MODE} \
    OPENSSL_FIPS=${OPENSSL_FIPS} \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/aigateway/.hf \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_PATH=/home/aigateway/app/venv \
    POETRY_CONFIG_DIR=/home/aigateway/app/.config/pypoetry \
    POETRY_DATA_DIR=/home/aigateway/app/.local/share/pypoetry \
    POETRY_CACHE_DIR=/home/aigateway/app/.cache/pypoetry \
    ENABLE_DUO_WORKFLOW_SERVICE=true

RUN id aigateway 2>/dev/null || useradd aigateway && \
    mkdir -p /home/aigateway/app && \
    chown -R aigateway:aigateway /home/aigateway/

WORKDIR /home/aigateway/app

RUN dnf install -y --nodocs \
    https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm \
    && dnf install -y --nodocs \
    findutils \
    parallel \
    && dnf clean all

RUN pip install "poetry==$POETRY_VERSION"

RUN mkdir -p -m 777 $POETRY_CONFIG_DIR $POETRY_DATA_DIR $POETRY_CACHE_DIR

COPY poetry.lock pyproject.toml ./
COPY README.md README.md
COPY ai_gateway/ ai_gateway/
COPY duo_workflow_service/ duo_workflow_service/
COPY lib/ lib/
COPY contract/ contract/
COPY scripts/ scripts/
COPY vendor/ vendor/

##
## Intermediate image contains build dependencies
##
FROM base-image AS install-image

RUN dnf install -y \
    gcc \
    gcc-c++ \
    make \
    python3.12-devel \
    libstdc++-static \
    && dnf clean all

RUN poetry install --compile --no-interaction --no-ansi --no-cache --only main

##
## Final image
##
FROM base-image AS final

USER aigateway

COPY --chown=aigateway:aigateway --from=install-image /home/aigateway/app/venv/ /home/aigateway/app/venv/

# Verify FIPS mode
RUN poetry run python -c "import ssl; print('OpenSSL version:', ssl.OPENSSL_VERSION); print('FIPS capable:', hasattr(ssl, '_fips_mode'))" || echo "FIPS verification info unavailable"

USER 0

RUN mkdir /home/aigateway/hardening

RUN curl --header "PRIVATE-TOKEN: $GITLAB_API_KEY" \
    --location \
    "https://gitlab.com/api/v4/projects/75557326/packages/generic/hardening/1.0.0/hardening.tar.gz" \
    | tar xvz -C /home/aigateway/hardening --strip-components=4

# Execute hardening scripts
RUN set -ex; \
    for f in /home/aigateway/hardening/*.sh; do \
        sh "$f"; \
    done

# Clean up hardening directory
RUN rm -rf /home/aigateway/hardening

EXPOSE 5052

CMD ["./scripts/run.sh"]
