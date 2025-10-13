FROM registry.access.redhat.com/ubi9/python-312-minimal:latest AS base-test

# Set FIPS environment variables
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/home/aigateway/.hf \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=2.2.1 \
    POETRY_VIRTUALENVS_PATH=/home/aigateway/app/venv \
    POETRY_CONFIG_DIR=/home/aigateway/app/.config/pypoetry \
    POETRY_DATA_DIR=/home/aigateway/app/.local/share/pypoetry \
    POETRY_CACHE_DIR=/home/aigateway/app/.cache/pypoetry \
    FIPS=1 \
    OPENSSL_FORCE_FIPS_MODE=1 \
    OPENSSL_FIPS=1