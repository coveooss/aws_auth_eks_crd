# CRD controller for AWS EKS Authenticator

[aws-iam-authenticator](https://github.com/kubernetes-sigs/aws-iam-authenticator) recently introduced the possibility to
use custom resources to configure roles and user bindings.
However, this version of the app is not available in EKS and is not planned
to [at this moment](https://github.com/aws/containers-roadmap/issues/550).
So here is an operator to reflect IamIdentityMappings changes in the aws-auth configmap.

## Get started

Language: Python 3.10+

### Step 1: Configure your Python environment

1. Install [pyenv](https://github.com/pyenv/pyenv#installation) to manage your Python environment
2. Install Python 3.10.13

```bash
  pyenv install 3.10.13
```

3. In the repository, switch to the chosen Python version

```bash
  pyenv local 3.10.13
```

### Step 2: Install [Coveo Stew](https://github.com/coveo/stew) dependencies (CI)

1. [Install pipx](https://pypa.github.io/pipx/)
2. [Install Poetry](https://python-poetry.org/docs/#installation)
3. [Install Stew](https://github.com/coveo/stew#installation)

### Step 3: Install Python dependencies

1. Open a pyenv shell for the correct python version

```bash
pyenv shell 3.10.13
```

2. Configure Poetry to use our Python version

```bash
poetry env use $(pyenv which python)
```

3. Install the dependencies with Poetry for the first time.

```bash
poetry install
```

4. Run Stew.

```bash
stew ci
```

### Step 4: Set up PyCharm's environment

1. Find the path of the virtual environment created by Poetry:

```bash
  poetry env info
```

2. Set that poetry environment as
   your [PyCharm virtual environment for the project](https://www.jetbrains.com/help/pycharm/creating-virtual-environment.html)

## Test Operator

```kopf run --dev --debug --standalone --liveness=http://:8080/healthz src/kubernetes_operator/iam_mapping.py```

You can also test the operator locally in a minikube context.

| WARNING: Make sure you change your context to minikube before doing these commands. |
|-------------------------------------------------------------------------------------|

1. Create a test config-map `kubectl apply -f kubernetes/test/configmap.yaml`
2. Create the IamIdentityMapping crd `kubectl apply -f kubernetes/iamidentitymappings.yaml`
3. Inspect the current state of the configmap with `kubectl get cm -n kube-system aws-auth -o yaml`
4. Start the operator in
   minikube `kopf run --dev --debug --standalone --liveness=http://:8080/healthz src/kubernetes_operator/iam_mapping.py`
5. Create, in a different terminal, an IamIdentityMapping `kubectl apply -f kubernetes/test/test-iam-rolearn.yaml`
6. Verify the change is applied by the operator in the configmap with `kubectl get cm -n kube-system aws-auth -o yaml`

## Deploy

### With kubectl

- Deploy the CRD definition

```kubectl apply -f kubernetes/iamidentitymapping.yaml```

- Deploy the operator

```kubectl apply -f kubernetes/auth-operator.yaml```

### With Kustomize

```bash
# Choose a specific ref and tag if needed
REF=master
TAG=0.6.4

cat <<EOF > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: kube-system

resources:
- https://github.com/coveooss/aws_auth_eks_crd//kubernetes/?ref=$REF

images:
- name: coveo/aws-auth-operator:0.1
  newName: ghcr.io/coveooss/aws_auth_eks_crd
  newTag: $TAG

EOF

# Deploy
kustomize build . | kubectl apply -f -
```
