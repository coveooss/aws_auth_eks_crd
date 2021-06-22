from pathlib import Path

import kopf
import yaml
import logging
from kubernetes import client, config
from kubernetes.client.models.v1_config_map import V1ConfigMap

logger = logging.getLogger("operator")

try:
    config.load_kube_config()
except Exception as e:
    logger.info(
        "Could not load kubeconfig. Error is : %s.\nAssuming we are in a kubernetes cluster", e)
    try:
        config.load_incluster_config()
    except Exception as e:
        raise (Exception("No k8s config suitable, exiting (%s)", format(e)))
else:
    logging.info("Using Kubernetes local configuration")

API = client.CoreV1Api()
custom_objects_API = client.CustomObjectsApi()
GROUP = "iamauthenticator.k8s.aws"
VERSION = "v1alpha1"
PLURAL = "iamidentitymappings"


@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.create(GROUP, VERSION, PLURAL)
async def create_mapping(spec: dict, diff: list, **kwargs) -> None:
    # Do nothing when we have no diff
    if len(diff) < 1:
        return dict()
    logging.info(spec)
    logging.info(diff)
    sanitize_spec = dict(spec)
    cm = API.read_namespaced_config_map("aws-auth", "kube-system")
    if spec.get("userarn") is not None:
        logger.info("Mapping for user %s as %s to %s",
                    spec["userarn"], spec["username"], spec["groups"])

        users = get_user_mapping(cm)
        updated_mapping = ensure_identity(sanitize_spec, users)
        await apply_user_mapping(cm, updated_mapping)
    else:
        logger.info("Mapping for user %s as %s to %s",
                    spec["rolearn"], spec["username"], spec["groups"])

        roles = get_role_mapping(cm)
        updated_mapping = ensure_identity(sanitize_spec, roles)
        await apply_role_mapping(cm, updated_mapping)


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def delete_mapping(spec: dict, **kwargs) -> None:

    cm = API.read_namespaced_config_map("aws-auth", "kube-system")
    if spec.get("userarn") is not None:
        logger.info("Delete mapping for user %s as %s to %s",
                    spec["userarn"], spec["username"], spec["groups"])
        users = get_user_mapping(cm)
        updated_mapping = delete_identity(spec, users)
        await apply_user_mapping(cm, updated_mapping)
    else:
        logger.info("Delete mapping for user %s as %s to %s",
                    spec["rolearn"], spec["username"], spec["groups"])
        roles = get_role_mapping(cm)
        updated_mapping = delete_identity(spec, roles)
        await apply_role_mapping(cm, updated_mapping)


@kopf.on.startup()
def on_startup(logger: logger, **kwargs) -> None:
    # Do a full synchronization at the start
    logger.info("Deploy CRD definition")
    deploy_crd_definition()
    logger.info("Reconcile all existing ressources")
    full_synchronize()


@kopf.on.probe(id="sync")
def get_monitoring_status(**kwargs) -> bool:
    return check_synchronization()


def check_synchronization() -> bool:
    cm = API.read_namespaced_config_map("aws-auth", "kube-system")
    identity_mappings = custom_objects_API.list_cluster_custom_object(
        GROUP, VERSION, PLURAL)

    users_in_cm = get_user_mapping(cm)
    users_in_cm = users_in_cm if isinstance(users_in_cm, list) else list()
    users_in_cm = [u["username"] for u in users_in_cm]

    users_in_crd = [im["spec"]["username"]
                    for im in identity_mappings["items"]]

    if set(users_in_cm) == set(users_in_crd):
        return True
    else:
        # Raise exception to make the monitoring probe fail
        raise Exception("monitoring check result : out-of-sync")


def deploy_crd_definition() -> None:
    crd_file_path = get_project_root() / "kubernetes/iamidentitymappings.yaml"
    with open(crd_file_path.resolve(), "r") as stream:
        body = yaml.safe_load(stream)
    extensions_api = client.ApiextensionsV1beta1Api()
    crds = extensions_api.list_custom_resource_definition()
    crds_name = {
        x["metadata"]["name"]: x["metadata"]
        ["resource_version"] for x in crds.to_dict()["items"]
    }
    crd_name = body["metadata"]["name"]
    if crd_name not in crds_name.keys():
        try:
            extensions_api.create_custom_resource_definition(body)
        except ValueError as err:
            if not err.args[0] == "Invalid value for `conditions`, must not be `None`":
                raise err
    else:
        body["metadata"]["resourceVersion"] = crds_name[crd_name]
        extensions_api.replace_custom_resource_definition(
            crd_name, body)


def full_synchronize() -> None:
    # Get Kubernetes" objects
    cm = API.read_namespaced_config_map("aws-auth", "kube-system")
    identity_mappings = custom_objects_API.list_cluster_custom_object(
        GROUP, VERSION, PLURAL)
    users = get_user_mapping(cm)
    users = users if type(users) == "list" else list()
    for im in identity_mappings["items"]:
        users = ensure_identity(im["spec"], users)
    apply_user_mapping(cm, users)


def get_user_mapping(cm: V1ConfigMap) -> list:
    try:
        return yaml.safe_load(cm.data["mapUsers"])
    except:
        return []


def get_role_mapping(cm: V1ConfigMap) -> list:
    try:
        return yaml.safe_load(cm.data["mapRoles"])
    except:
        return []


async def apply_user_mapping(existing_cm: V1ConfigMap, user_mapping: list) -> None:
    existing_cm.data["mapUsers"] = yaml.safe_dump(user_mapping)
    API.patch_namespaced_config_map("aws-auth", "kube-system", existing_cm)


async def apply_role_mapping(existing_cm: V1ConfigMap, role_mapping: list) -> None:
    existing_cm.data["mapRoles"] = yaml.safe_dump(role_mapping)
    API.patch_namespaced_config_map("aws-auth", "kube-system", existing_cm)


def ensure_identity(identity: dict, identity_list: list) -> list:
    for i, existing_identity in enumerate(identity_list):
        # Handle existing identity
        if existing_identity["username"] == identity["username"]:
            identity_list[i] = identity
            return identity_list
    # Handle new identity
    else:
        identity_list.append(identity)
    return identity_list


def delete_identity(identity: dict, identity_list: list) -> list:
    for i, existing_user in enumerate(identity_list):
        if existing_user["username"] == identity["username"]:
            del identity_list[i]
            return identity_list
    else:
        logger.warning(
            "Want to delete %s, but not found", identity["username"])
    return identity_list


def get_project_root() -> Path:
    """Return the root folder.
    If the utils file is moved, this relative path NEEDS to be changed accordingly.
    """
    path = Path(__file__)
    return path.parent.parent.parent
