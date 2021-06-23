# CRD controller for AWS EKS Authenticator
[aws-iam-authenticator](https://github.com/kubernetes-sigs/aws-iam-authenticator) recently introduced the possibility to use custom resources to configure roles and user bindings.
However, this version of the app is not available in EKS and is not planned to [at this moment](https://github.com/aws/containers-roadmap/issues/550).
So here is an operator to reflect changes in IamIdentityMappings in the aws-auth configmap.

## Get started
1. Install [poetry](https://python-poetry.org/)
2. Install the dependencies in a virtual environment `poetry install`
3. Add the git pre-commit hook `poetry run pre-commit install`.
4. Make your IDE use the virtualenv that was created by poetry.

To run all tests/linters, use `pre-commit run` after staging your changes

---
**NOTE**

Every commit will be checked against all linters with pre-commit. If it fails, simply fix the issues, stage new changes, and commit again.

---

## Test Operator

```kopf run --dev --debug --standalone --liveness=http://:8080/healthz src/kubernetes_operator/iam_mapping.py```

You can also test the operator locally in a minikube context.

| WARNING: Make sure you change your context to minikube before doing these commands. |
| --- |

1. Create a test config-map `kubectl apply -f kubernetes/test/configmap.yaml`
2. Start the operator in minikube `kopf run --dev --debug --standalone --liveness=http://:8080/healthz src/kubernetes_operator/iam_mapping.py`
3. Create, in a different terminal, an IamIdentityMapping `kubectl apply -f kubernetes/test/test-iam-rolearn.yaml`
4. Verify the change is applied by the operator in the configmap with `kubectl get cm -n kube-system aws-auth -o yaml`

## Usage

### Deploy CRD definition

```kubectl apply -f kubernetes/iamidentitymapping.yaml```

### Deploy operator

```kubectl apply -f kubernetes/auth-operator.yaml```
