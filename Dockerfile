FROM python:3.13-alpine@sha256:a70b35b575e33d951e3f9d3fe94163ef0fd338c22552bc587a1b098a87ed6184

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
