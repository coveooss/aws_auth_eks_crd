import asyncio
from unittest.mock import patch, MagicMock

import pytest
import yaml
from kubernetes import client

import src.kubernetes_operator.iam_mapping as iam_mapping

BASE_PATH = "src.kubernetes_operator.iam_mapping"

SPEC_USER_MARK = {"groups": ["system:masters"], "userarn": "arn:aws:iam::000000000000:user/mark", "username": "mark"}
SPEC_USER_JOHNDOE = {
    "groups": ["system:masters", "some-other-group-namespace-admin"],
    "userarn": "arn:aws:iam::000000000000:user/johndoe",
    "username": "johndoe",
}
SPEC_CSEC_ADMIN = {
    "groups": ["user-group-csec-admin"],
    "rolearn": "arn:aws:iam::000000000000:role/sdm-eks-csec-admin",
    "username": "sdm-csec-admin",
}
SPEC_CSEC_MAINTENANCE = {
    "groups": ["user-group-csec-maintenance"],
    "rolearn": "arn:aws:iam::000000000000:role/sdm-eks-csec-maintenance",
    "username": "sdm-csec-maintenance",
}

DATA = {"mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN]), "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE])}

CONFIGMAP = client.V1ConfigMap(api_version="v1", kind="ConfigMap", data=DATA, metadata={"key": "some_metadata"})

DIFF_NEW_USER_MARK = [
    (
        "add",
        (),
        None,
        {"spec": SPEC_USER_MARK},
    )
]
DIFF_NEW_ROLE_CSEC_MAINTENANCE = [
    (
        "add",
        (),
        None,
        {"spec": SPEC_CSEC_MAINTENANCE},
    )
]

IAM_IDENTITY_MAPPINGS = {
    "apiVersion": "iamauthenticator.k8s.aws/v1alpha1",
    "items": [
        {
            "apiVersion": "iamauthenticator.k8s.aws/v1alpha1",
            "kind": "IAMIdentityMapping",
            "spec": {
                "groups": SPEC_USER_JOHNDOE["groups"],
                "userarn": SPEC_USER_JOHNDOE["userarn"],
                "username": SPEC_USER_JOHNDOE["username"],
            },
        },
        {
            "apiVersion": "iamauthenticator.k8s.aws/v1alpha1",
            "kind": "IAMIdentityMapping",
            "spec": {
                "groups": SPEC_CSEC_ADMIN["groups"],
                "rolearn": SPEC_CSEC_ADMIN["rolearn"],
                "username": SPEC_CSEC_ADMIN["username"],
            },
        },
    ],
    "kind": "IAMIdentityMappingList",
    "metadata": {"continue": "", "resourceVersion": "40281"},
}

GROUP = "iamauthenticator.k8s.aws"
VERSION = "v1alpha1"
PLURAL = "iamidentitymappings"


@pytest.fixture
def api_client():
    with patch(f"{BASE_PATH}.API") as client_mock:
        client_mock.read_namespaced_config_map.return_value = CONFIGMAP
        yield client_mock


@pytest.fixture
def custom_objects_api():
    with patch(f"{BASE_PATH}.custom_objects_API") as custom_objects_api_mock:
        custom_objects_api_mock.list_cluster_custom_object.return_value = IAM_IDENTITY_MAPPINGS
        yield custom_objects_api_mock


@pytest.fixture
def create_mock_coroutine(monkeypatch):
    def _create_mock_patch_coroutine(to_patch=None):
        mock = MagicMock()

        async def _coro(*args, **kwargs):
            return mock(*args, **kwargs)

        if to_patch:
            monkeypatch.setattr(to_patch, _coro)

        return mock, _coro

    return _create_mock_patch_coroutine


@pytest.fixture
def mock_apply_identity_mappings(create_mock_coroutine):
    mock, _ = create_mock_coroutine(to_patch=f"{BASE_PATH}.apply_identity_mappings")
    return mock


def run_sync(coroutine):
    return asyncio.run(coroutine)


def test_create_mapping_userarn(mock_apply_identity_mappings, api_client):
    run_sync(iam_mapping.create_mapping(spec=SPEC_USER_MARK, diff=DIFF_NEW_USER_MARK))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN, SPEC_USER_MARK])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_create_mapping_rolearn(mock_apply_identity_mappings, api_client):
    run_sync(iam_mapping.create_mapping(spec=SPEC_CSEC_MAINTENANCE, diff=DIFF_NEW_ROLE_CSEC_MAINTENANCE))

    mock_apply_identity_mappings.assert_called_with(
        CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN, SPEC_CSEC_MAINTENANCE]
    )
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_delete_mapping_userarn(mock_apply_identity_mappings, api_client):
    run_sync(iam_mapping.delete_mapping(spec=SPEC_USER_JOHNDOE))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_CSEC_ADMIN])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_delete_mapping_rolearn(mock_apply_identity_mappings, api_client):
    run_sync(iam_mapping.delete_mapping(spec=SPEC_CSEC_ADMIN))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_check_synchronization_no_diff(api_client, custom_objects_api):
    assert iam_mapping.check_synchronization()
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_check_synchronization_with_diff(api_client, custom_objects_api):
    modified_iam_identity_mapping = custom_objects_api.list_cluster_custom_object.return_value
    modified_iam_identity_mapping["items"].pop()
    custom_objects_api.list_cluster_custom_object.return_value = modified_iam_identity_mapping

    with pytest.raises(Exception):
        iam_mapping.check_synchronization()
        api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
        custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_full_synchronize(mock_apply_identity_mappings, api_client, custom_objects_api):
    iam_mapping.full_synchronize()

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)
