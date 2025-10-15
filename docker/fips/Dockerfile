# Use official Red Hat UBI9 Python 3.12 minimal image for FIPS compliance
FROM registry.access.redhat.com/ubi9/python-312-minimal:latest AS base-image

# When trying to install system requirements, we need to have a user root for
# system packages with microdnf before switching to the aigateway user, 
# but the base UBI9 Python minimal image runs as a non-root user by default.
USER 0

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
FROM registry.access.redhat.com/ubi9/python-312:latest AS install-image

USER 0
WORKDIR /home/aigateway/app

COPY --from=base-image /home/aigateway/app/poetry.lock /home/aigateway/app/pyproject.toml ./
COPY --from=base-image /home/aigateway/app/README.md ./
COPY --from=base-image /home/aigateway/app/ai_gateway ./ai_gateway
COPY --from=base-image /home/aigateway/app/duo_workflow_service ./duo_workflow_service
COPY --from=base-image /home/aigateway/app/lib ./lib
COPY --from=base-image /home/aigateway/app/contract ./contract
COPY --from=base-image /home/aigateway/app/scripts ./scripts
COPY --from=base-image /home/aigateway/app/vendor ./vendor

ENV POETRY_VERSION=2.2.1 \
    POETRY_VIRTUALENVS_PATH=/home/aigateway/app/venv \
    CYTHON_PEP489_MULTI_PHASE_INIT=0

RUN pip install "poetry==$POETRY_VERSION"

# Install only necessary build dependencies
RUN dnf install -y \
    gcc \
    gcc-c++ \
    make \
    python3.12-devel \
    libstdc++-static \
    findutils \
    && dnf clean all

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
RUN poetry run python -c "import ssl; print('OpenSSL version:', ssl.OPENSSL_VERSION); print('FIPS capable:', hasattr(ssl, '_fips_mode'))" || echo "FIPS verification info unavailable"

# RUN poetry run python scripts/bootstrap.py

EXPOSE 5052

CMD ["./scripts/run.sh"]