# Use official Red Hat UBI9 Python 3.12 minimal image for FIPS compliance
FROM registry.access.redhat.com/ubi9/python-312-minimal:latest AS base-image

ARG FIPS=1
ARG OPENSSL_FORCE_FIPS_MODE=1
ARG OPENSSL_FIPS=1
ARG POETRY_VERSION=2.2.1

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
    POETRY_CACHE_DIR=/home/aigateway/app/.cache/pypoetry

ENV ENABLE_DUO_WORKFLOW_SERVICE=true

WORKDIR /home/aigateway/app

COPY poetry.lock pyproject.toml ./
RUN pip install "poetry==$POETRY_VERSION"
RUN microdnf install -y --nodocs findutils && microdnf clean all
RUN mkdir -p -m 777 $POETRY_CONFIG_DIR $POETRY_DATA_DIR $POETRY_CACHE_DIR

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

RUN microdnf install -y \
    gcc \
    gcc-c++ \
    make \
    python3-devel \
    curl \
    findutils \
    && microdnf clean all

RUN poetry install --compile --no-interaction --no-ansi --no-cache --only main

##
## Final image
##
FROM base-image AS final

RUN microdnf install -y findutils && microdnf clean all

RUN useradd aigateway
RUN chown -R aigateway:aigateway /home/aigateway/
USER aigateway

COPY --chown=aigateway:aigateway --from=install-image /home/aigateway/app/venv/ /home/aigateway/app/venv/

# Use poetry run python
RUN poetry run python -c "import ssl; print('FIPS mode active:', ssl.FIPS_mode())" || echo "FIPS verification failed"

RUN poetry run python scripts/bootstrap.py

EXPOSE 5052

CMD ["./scripts/run.sh"]