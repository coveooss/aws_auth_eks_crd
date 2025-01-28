FROM python:3.13-alpine@sha256:f9d772b2b40910ee8de2ac2b15ff740b5f26b37fc811f6ada28fce71a2542b0e

LABEL description="Kubernetes operator to sync IamIdentityMappings to the aws-auth configmap"
LABEL source.repository="aws_auth_eks_crd"
LABEL source.dockerfile="Dockerfile"

RUN apk update --no-cache && apk upgrade --no-cache && apk add build-base
ADD . /app/
WORKDIR /app

RUN python -m pip install .

RUN addgroup -S operatorgroup
RUN adduser --system --ingroup operatorgroup --disabled-password --no-create-home --shell /sbin/nologin k8soperator

USER k8soperator

ENTRYPOINT ["/usr/local/bin/kopf", "run", "src/kubernetes_operator/iam_mapping.py"]
