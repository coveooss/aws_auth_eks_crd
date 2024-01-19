import asyncio
import logging
from os import environ
from unittest.mock import MagicMock, patch

import yaml
from pytest import fixture, raises

from kubernetes import client

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
SPEC_USER_SYSTEM_NODE_TO_IGNORE = {
    "groups": ["system:bootstrappers", "system:nodes"],
    "userarn": "arn:aws:iam::000000000000:role/dev-infra-us-east-000000000000000000000000000",
    "username": "system:node:{{EC2PrivateDNSName}}",
}

DATA = {"mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN]), "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE])}
DATA_MISSING_MAPUSERS = {"mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN])}
DATA_MISSING_MAPROLES = {"mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE])}

CONFIGMAP = client.V1ConfigMap(api_version="v1", kind="ConfigMap", data=DATA, metadata={"key": "some_metadata"})
CONFIGMAP_MISSING_MAPUSERS = client.V1ConfigMap(
    api_version="v1", kind="ConfigMap", data=DATA_MISSING_MAPUSERS, metadata={"key": "some_metadata"}
)
CONFIGMAP_MISSING_MAPROLES = client.V1ConfigMap(
    api_version="v1", kind="ConfigMap", data=DATA_MISSING_MAPROLES, metadata={"key": "some_metadata"}
)
CONFIGMAP_MISSING_DATA = client.V1ConfigMap(
    api_version="v1", kind="ConfigMap", data={}, metadata={"key": "some_metadata"}
)
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


@fixture(autouse=True)
def no_config_needed(login_mocks):
    pass


@fixture
def api_client():
    with patch(f"{BASE_PATH}.API") as client_mock:
        client_mock.read_namespaced_config_map.return_value = CONFIGMAP
        yield client_mock


@fixture
def custom_objects_api():
    with patch(f"{BASE_PATH}.custom_objects_API") as custom_objects_api_mock:
        custom_objects_api_mock.list_cluster_custom_object.return_value = IAM_IDENTITY_MAPPINGS
        yield custom_objects_api_mock


@fixture
def create_mock_coroutine(monkeypatch):
    def _create_mock_patch_coroutine(to_patch=None):
        mock = MagicMock()

        async def _coro(*args, **kwargs):
            return mock(*args, **kwargs)

        if to_patch:
            monkeypatch.setattr(to_patch, _coro)

        return mock, _coro

    return _create_mock_patch_coroutine


@fixture
def mock_apply_identity_mappings(create_mock_coroutine):
    mock, _ = create_mock_coroutine(to_patch=f"{BASE_PATH}.apply_cm_identity_mappings")
    return mock


def run_sync(coroutine):
    return asyncio.run(coroutine)


def test_create_mapping_userarn(mock_apply_identity_mappings, api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.create_mapping(spec=SPEC_USER_MARK, diff=DIFF_NEW_USER_MARK))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN, SPEC_USER_MARK])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_create_mapping_rolearn(mock_apply_identity_mappings, api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.create_mapping(spec=SPEC_CSEC_MAINTENANCE, diff=DIFF_NEW_ROLE_CSEC_MAINTENANCE))

    mock_apply_identity_mappings.assert_called_with(
        CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN, SPEC_CSEC_MAINTENANCE]
    )
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_update_mapping_userarn(mock_apply_identity_mappings, api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    spec_user_johndoe_updated = {
        "groups": ["system:masters", "some-other-group-namespace-admin", "new-group-to-update"],
        "userarn": "arn:aws:iam::000000000000:user/johndoe",
        "username": "johndoe",
    }

    # Content of the diff doesnt matter as long as it isn't an empty list
    run_sync(iam_mapping.create_mapping(spec=spec_user_johndoe_updated, diff=DIFF_NEW_USER_MARK))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [spec_user_johndoe_updated, SPEC_CSEC_ADMIN])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_delete_mapping_userarn(mock_apply_identity_mappings, api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.delete_mapping(spec=SPEC_USER_JOHNDOE))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_CSEC_ADMIN])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_delete_mapping_rolearn(mock_apply_identity_mappings, api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.delete_mapping(spec=SPEC_CSEC_ADMIN))

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")


def test_check_synchronization_no_diff(api_client, custom_objects_api):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    assert iam_mapping.check_synchronization()
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_check_synchronization_no_diff_with_ignored_identity(api_client, custom_objects_api):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    data = {
        "mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN, SPEC_USER_SYSTEM_NODE_TO_IGNORE]),
        "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE]),
    }
    configmap_with_ignore_mapping = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=data, metadata={"key": "some_metadata"}
    )
    api_client.read_namespaced_config_map.return_value = configmap_with_ignore_mapping

    assert iam_mapping.check_synchronization()
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


@patch.dict(
    environ, {"IGNORED_CM_IDENTITIES": f"{SPEC_USER_MARK.get('username')},{SPEC_CSEC_MAINTENANCE.get('username')}"}
)
def test_check_synchronization_no_diff_with_ignored_identity_env(api_client, custom_objects_api):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    data = {
        "mapRoles": yaml.safe_dump([SPEC_CSEC_MAINTENANCE, SPEC_CSEC_ADMIN, SPEC_USER_SYSTEM_NODE_TO_IGNORE]),
        "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE, SPEC_USER_MARK]),
    }
    configmap_with_ignore_mapping = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=data, metadata={"key": "some_metadata"}
    )
    api_client.read_namespaced_config_map.return_value = configmap_with_ignore_mapping

    assert iam_mapping.check_synchronization()
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_check_synchronization_with_diff(api_client, custom_objects_api):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    modified_iam_identity_mapping = custom_objects_api.list_cluster_custom_object.return_value
    modified_iam_identity_mapping["items"].pop()
    custom_objects_api.list_cluster_custom_object.return_value = modified_iam_identity_mapping

    with raises(Exception):
        iam_mapping.check_synchronization()
        api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
        custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_full_synchronize(mock_apply_identity_mappings, api_client, custom_objects_api):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    iam_mapping.full_synchronize()

    mock_apply_identity_mappings.assert_called_with(CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN])
    api_client.read_namespaced_config_map.assert_called_with("aws-auth", "kube-system")
    custom_objects_api.list_cluster_custom_object.assert_called_with(GROUP, VERSION, PLURAL)


def test_apply_cm_identity_mappings_with_userarn(api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.apply_cm_identity_mappings(CONFIGMAP, [SPEC_USER_JOHNDOE]))

    expected_cm_data = {"mapRoles": yaml.safe_dump([]), "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE])}
    expected_configmap = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=expected_cm_data, metadata={"key": "some_metadata"}
    )
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", expected_configmap)


def test_apply_cm_identity_mappings_with_rolearn(api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.apply_cm_identity_mappings(CONFIGMAP, [SPEC_CSEC_ADMIN]))

    expected_cm_data = {"mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN]), "mapUsers": yaml.safe_dump([])}
    expected_configmap = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=expected_cm_data, metadata={"key": "some_metadata"}
    )
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", expected_configmap)


def test_apply_cm_identity_mappings_with_unknown_mapping(api_client, caplog):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    caplog.set_level(logging.WARNING)
    some_unknown_spec = {"groups": ["system:masters"], "arn": "arn:aws:iam::000000000000:user/bob", "username": "bob"}

    run_sync(iam_mapping.apply_cm_identity_mappings(CONFIGMAP, [some_unknown_spec]))

    expected_cm_data = {"mapRoles": yaml.safe_dump([]), "mapUsers": yaml.safe_dump([])}
    expected_configmap = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=expected_cm_data, metadata={"key": "some_metadata"}
    )
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", expected_configmap)

    assert caplog.messages
    for message in caplog.messages:
        assert message.find("Unrecognized mapping.") != -1


def test_apply_cm_identity_mappings_with_userarn_and_rolearn_and_unknown_mapping(api_client, caplog):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    caplog.set_level(logging.WARNING)
    some_unknown_spec = {"groups": ["system:masters"], "arn": "arn:aws:iam::000000000000:user/bob", "username": "bob"}

    run_sync(iam_mapping.apply_cm_identity_mappings(CONFIGMAP, [SPEC_USER_JOHNDOE, SPEC_CSEC_ADMIN, some_unknown_spec]))

    expected_cm_data = {"mapRoles": yaml.safe_dump([SPEC_CSEC_ADMIN]), "mapUsers": yaml.safe_dump([SPEC_USER_JOHNDOE])}
    expected_configmap = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=expected_cm_data, metadata={"key": "some_metadata"}
    )
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", expected_configmap)
    assert caplog.messages
    for message in caplog.messages:
        assert message.find("Unrecognized mapping.") != -1


def test_apply_cm_identity_mappings_with_no_mapping(api_client):
    import src.kubernetes_operator.iam_mapping as iam_mapping

    run_sync(iam_mapping.apply_cm_identity_mappings(CONFIGMAP, []))

    expected_cm_data = {"mapRoles": yaml.safe_dump([]), "mapUsers": yaml.safe_dump([])}
    expected_configmap = client.V1ConfigMap(
        api_version="v1", kind="ConfigMap", data=expected_cm_data, metadata={"key": "some_metadata"}
    )
    api_client.patch_namespaced_config_map.assert_called_with("aws-auth", "kube-system", expected_configmap)


def test_get_cm_identity_mappings_with_empty_mapusers_skips():
    import src.kubernetes_operator.iam_mapping as iam_mapping

    ret = iam_mapping.get_cm_identity_mappings(CONFIGMAP_MISSING_MAPUSERS)

    assert len(ret) == 1
    assert ret[0] == SPEC_CSEC_ADMIN


def test_get_cm_identity_mappings_with_empty_maproles_skips():
    import src.kubernetes_operator.iam_mapping as iam_mapping

    ret = iam_mapping.get_cm_identity_mappings(CONFIGMAP_MISSING_MAPROLES)

    assert len(ret) == 1
    assert ret[0] == SPEC_USER_JOHNDOE


def test_get_cm_identity_mappings_with_empty_configmap_returns_no_identity():
    import src.kubernetes_operator.iam_mapping as iam_mapping

    ret = iam_mapping.get_cm_identity_mappings(CONFIGMAP_MISSING_DATA)

    assert len(ret) == 0
