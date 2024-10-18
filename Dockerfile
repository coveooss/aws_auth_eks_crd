FROM python:3.13-alpine@sha256:81362dd1ee15848b118895328e56041149e1521310f238ed5b2cdefe674e6dbf

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
