from unittest.mock import patch, MagicMock

import pytest as pytest

import src.kubernetes_operator.iam_mapping as iam_mapping

BASE_PATH = "src.kubernetes_operator.iam_mapping"

CONFIG_MAP = {
    "apiVersion": "v1",
    "data": {
        "mapRoles": "- groups:\n  - user-group-namespace-admin\n  rolearn: "
                    "arn:aws:iam::000000000000:role/sdm-eks-namespace-admin\n  username: sdm-namespace-admin\n",
        "mapUsers": "- groups:\n  - system:masters\n  userarn: arn:aws:iam::000000000000:user/johndoe\n  username: "
                    "johndoe\n "
    },
    "kind": "ConfigMap",
    "metadata": {
        "annotations": {
            "kubectl.kubernetes.io/last-applied-configuration": "{\"apiVersion\":\"v1\",\"data\":{"
                                                                "\"config.yaml\":\"clusterID: "
                                                                "my-dev-cluster.example.com\\nserver:\\n  "
                                                                "mapRoles:\\n  - roleARN: "
                                                                "arn:aws:iam::000000000000:role/KubernetesAdmin\\n    "
                                                                "username: kubernetes-admin\\n    groups:\\n    - "
                                                                "system:masters\\n  mapUsers:\\n  - userARN: "
                                                                "arn:aws:iam::000000000000:user/Alice\\n    username: "
                                                                "alice\\n    groups:\\n    - system:masters\\n\"},"
                                                                "\"kind\":\"ConfigMap\",\"metadata\":{"
                                                                "\"annotations\":{},\"labels\":{"
                                                                "\"k8s-app\":\"aws-iam-authenticator\"},"
                                                                "\"name\":\"aws-auth\","
                                                                "\"namespace\":\"kube-system\"}}\n "
        },
        "creationTimestamp": "2021-06-22T14:22:08Z",
        "labels": {
            "k8s-app": "aws-iam-authenticator"
        },
        "name": "aws-auth",
        "namespace": "kube-system",
        "resourceVersion": "7773",
        "uid": "8ebe6c19-2934-4552-9af0-5e6aeaa15805"
    }
}

SPEC1 = {'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/alice', 'username': 'alice'}
DIFF1 = [('add', (), None, {'spec': {'groups': ['system:masters'], 'userarn': 'arn:aws:iam::000000000000:user/alice', 'username': 'alice'}}),]


@pytest.fixture
def api_client():
    client_mock = MagicMock()
    client_mock.read_namespaced_config_map.return_value = CONFIG_MAP
    with patch(f"{BASE_PATH}.client", return_value=client_mock):
        yield client_mock


@patch(f"{BASE_PATH}.apply_user_mapping")
def test_create_mapping_userarn(apply_user_mapping_mock, api_client):
    iam_mapping.create_mapping(spec=SPEC1, diff=DIFF1)

