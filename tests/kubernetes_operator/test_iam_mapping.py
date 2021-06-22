import asyncio
from unittest import mock
from unittest.mock import patch, MagicMock

import pytest as pytest
import yaml
from kubernetes.client import ApiClient
from kubernetes import client

import src.kubernetes_operator.iam_mapping as iam_mapping

BASE_PATH = "src.kubernetes_operator.iam_mapping"

CONFIG_MAP_DATA = {
    "mapRoles": "- groups:\n  - user-group-namespace-admin\n  rolearn: "
                "arn:aws:iam::000000000000:role/sdm-eks-namespace-admin\n  username: sdm-namespace-admin\n",
    "mapUsers": "- groups:\n  - system:masters\n  userarn: arn:aws:iam::000000000000:user/johndoe\n  username: "
                "johndoe\n "
}
METADATA = {
    "annotations": {
        "kubectl.kubernetes.io/last-applied-configuration": "{\"apiVersion\":\"v1\",\"data\":{\"mapRoles\":\"- "
                                                            "roleARN: "
                                                            "arn:aws:iam::000000000000:role/KubernetesAdmin\\n  "
                                                            "username: kubernetes-admin\\n  groups:\\n  - "
                                                            "system:masters\\n\",\"mapUsers\":\"- userARN: "
                                                            "arn:aws:iam::000000000000:user/Alice\\n  username: "
                                                            "alice\\n  groups:\\n  - system:masters\\n\"},"
                                                            "\"kind\":\"ConfigMap\",\"metadata\":{"
                                                            "\"annotations\":{},\"labels\":{"
                                                            "\"k8s-app\":\"aws-iam-authenticator\"},"
                                                            "\"name\":\"aws-auth\","
                                                            "\"namespace\":\"kube-system\"}}\n "
    },
    "creationTimestamp": "2021-06-22T19:23:37Z",
    "labels": {
        "k8s-app": "aws-iam-authenticator"
    },
    "name": "aws-auth",
    "namespace": "kube-system",
    "resourceVersion": "17534",
    "uid": "eba376b5-cb10-4fe3-9199-4c602a85e0c7"
}

CONFIGMAP = client.V1ConfigMap(
    api_version="v1",
    kind="ConfigMap",
    data=CONFIG_MAP_DATA,
    metadata=METADATA
)

SPEC1 = {'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/mark', 'username': 'mark'}
DIFF1 = [('add', (), None, {'spec': {'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/mark',
                                     'username': 'mark'}})]


@pytest.fixture
def api_client():
    with patch(f"{BASE_PATH}.API") as client_mock:
        client_mock.read_namespaced_config_map.return_value = CONFIGMAP
        yield client_mock


def run_sync(coroutine):
    return asyncio.run(coroutine)


def test_create_mapping_userarn(api_client):
    run_sync(iam_mapping.create_mapping(spec=SPEC1, diff=DIFF1))

    CONFIGMAP.data["mapUsers"] = [{'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/johndoe'},
                                  {'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/mark'}]
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", CONFIGMAP)
