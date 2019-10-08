# CRD controller for AWS EKS Authenticator
[aws-iam-authenticator](https://github.com/kubernetes-sigs/aws-iam-authenticator) recently introduce the possibility to use custom resources to configure role and user binding. However this version of the app is not available in EKS and is not plan to, at this moment.
So here is an operator to handle userRole.

## Test Operator

```kopf run --dev --debug --standalone iam_mapping.py```

## Usage

### Deploy CRD definition

```kubectl apply -f kubernetes/iamidentitymapping.yaml```

### Deploy operator

```kubectl apply -f kubernetes/auth-operator.yaml```
