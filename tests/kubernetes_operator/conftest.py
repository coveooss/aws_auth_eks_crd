import dataclasses
from unittest.mock import Mock

import pytest


@dataclasses.dataclass(frozen=True, eq=False, order=False)
class LoginMocks:
    pykube_in_cluster: Mock = None
    pykube_from_file: Mock = None
    pykube_from_env: Mock = None
    client_in_cluster: Mock = None
    client_from_file: Mock = None


@pytest.fixture()
def login_mocks(mocker):
    """
    Make all client libraries potentially optional, but do not skip the tests:
    skipping the tests is the tests' decision, not this mocking fixture's one.
    """
    kwargs = {}
    try:
        import pykube
    except ImportError:
        pass
    else:
        cfg = pykube.KubeConfig(
            {
                "current-context": "self",
                "clusters": [{"name": "self", "cluster": {"server": "localhost"}}],
                "contexts": [{"name": "self", "context": {"cluster": "self", "namespace": "default"}}],
            }
        )
        kwargs.update(
            pykube_in_cluster=mocker.patch.object(pykube.KubeConfig, "from_service_account", return_value=cfg),
            pykube_from_file=mocker.patch.object(pykube.KubeConfig, "from_file", return_value=cfg),
            pykube_from_env=mocker.patch.object(pykube.KubeConfig, "from_env", return_value=cfg),
        )
    try:
        import kubernetes
    except ImportError:
        pass
    else:
        kwargs.update(
            client_in_cluster=mocker.patch.object(kubernetes.config, "load_incluster_config"),
            client_from_file=mocker.patch.object(kubernetes.config, "load_kube_config"),
        )
    return LoginMocks(**kwargs)
