FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS builder

# renovate: datasource=pypi depName=poetry
ARG POETRY_VERSION=2.5.2
# renovate: datasource=pypi depName=poetry-plugin-export
ARG POETRY_PLUGIN_EXPORT_VERSION=1.10.2

RUN apk add --no-cache build-base
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    "poetry==${POETRY_VERSION}" "poetry-plugin-export==${POETRY_PLUGIN_EXPORT_VERSION}"

WORKDIR /build
COPY pyproject.toml poetry.lock README.md ./
RUN poetry export --only main --format requirements.txt --output requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check --require-hashes -r requirements.txt

FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb

LABEL description="Kubernetes operator to sync IamIdentityMappings to the aws-auth configmap"
LABEL source.repository="aws_auth_eks_crd"
LABEL source.dockerfile="Dockerfile"

RUN addgroup -S operatorgroup \
    && adduser --system --ingroup operatorgroup --disabled-password --no-create-home --shell /sbin/nologin k8soperator

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY src ./src
COPY kubernetes/iamidentitymappings.yaml ./kubernetes/

USER k8soperator

ENTRYPOINT ["/opt/venv/bin/kopf", "run", "src/kubernetes_operator/iam_mapping.py"]
