"""Kubernetes operator to manage IamIdentityMappings in the aws-config configmap."""
import asyncio
import logging
from copy import deepcopy
from os import environ
from pathlib import Path
from typing import List

import kopf
import yaml
from kubernetes import client, config
from kubernetes.client.models.v1_config_map import V1ConfigMap

logger = logging.getLogger("operator")

try:
    config.load_kube_config()
except Exception as error:
    logger.info("Could not load kubeconfig. Error is : %s.\nAssuming we are in a kubernetes cluster", error)
    try:
        config.load_incluster_config()
    except Exception as error:
        error_str = format(error)
        raise Exception(f"No k8s config suitable, exiting ({error_str})") from error
else:
    logging.info("Using Kubernetes local configuration")

API = client.CoreV1Api()
custom_objects_API = client.CustomObjectsApi()
GROUP = "iamauthenticator.k8s.aws"
VERSION = "v1alpha1"
PLURAL = "iamidentitymappings"

# Allow some mappings in the aws-auth ConfigMap to exist without being defined
# in a IamIdentityMapping object.
IGNORED_CM_IDENTITIES = [
    # EKS worker nodes
    "system:node:{{EC2PrivateDNSName}}",
]


@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.create(GROUP, VERSION, PLURAL)
async def create_mapping(spec: dict, diff: list, **_) -> None:
    """Create/update an identity mapping in the aws-auth configmap with the corresponding IamIdentityMapping.

    This method accepts mappings for userarn and rolearn with groups.

    :param spec: The spec of the changed IamIdentityMapping
    :param diff: The diff created by the changed identity
    """

    # Do nothing when we have no diff
    if not diff:
        return

    sanitize_spec = dict(spec)
    configmap = API.read_namespaced_config_map("aws-auth", "kube-system")

    arn_field = spec["userarn"] if spec.get("userarn") else spec["rolearn"]
    logger.info("Mapping for user %s as %s to %s", arn_field, spec["username"], spec.get("groups", "(no group)"))

    identities = get_cm_identity_mappings(configmap)
    updated_mapping = ensure_identity(sanitize_spec, identities)
    await apply_cm_identity_mappings(configmap, updated_mapping)


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def delete_mapping(spec: dict, **_) -> None:
    """Delete the identity mapping in the aws-auth configmap corresponding to the deleted IamIdentityMapping.

    :param spec: The spec of the removed IamIdentityMapping
    """
    configmap = API.read_namespaced_config_map("aws-auth", "kube-system")

    arn_field = spec["userarn"] if spec.get("userarn") else spec["rolearn"]
    logger.info("Delete mapping for user %s as %s to %s", arn_field, spec["username"], spec.get("groups", "(no group)"))

    identity_mappings = get_cm_identity_mappings(configmap)
    updated_mappings = delete_identity(spec, identity_mappings)
    await apply_cm_identity_mappings(configmap, updated_mappings)


@kopf.on.startup()
def on_startup(logger, **_) -> None:
    """Deploy the CRD and synchronize the existing mappings on startup."""
    # Do a full synchronization at the start
    logger.info("Deploy CRD definition")
    deploy_crd_definition()
    logger.info("Reconcile all existing resources")
    full_synchronize()


@kopf.on.probe(id="sync")
def get_monitoring_status(**_) -> bool:
    """Check if the aws-auth configmap mappings are in sync with the IamIdentityMappings."""
    return check_synchronization()


def check_synchronization() -> bool:
    """Compare the aws-auth configmap to the IamIdentityMappings and return if they are in sync."""

    identity_mappings = custom_objects_API.list_cluster_custom_object(GROUP, VERSION, PLURAL)
    identities_in_crd = [im["spec"]["username"] for im in identity_mappings["items"]]

    configmap = API.read_namespaced_config_map("aws-auth", "kube-system")
    identities_in_cm = get_cm_identity_mappings(configmap)
    identities_in_cm = identities_in_cm if isinstance(identities_in_cm, list) else list()
    identities_in_cm = [u["username"] for u in identities_in_cm]

    # Allow some mappings in the aws-auth ConfigMap to exist without being defined
    # in an IamIdentityMapping object.
    identities_to_ignore: List[str] = deepcopy(IGNORED_CM_IDENTITIES)

    if "IGNORED_CM_IDENTITIES" in environ:
        identities_to_ignore = identities_to_ignore + environ.get("IGNORED_CM_IDENTITIES", "").split(",")

    identities_in_cm_set = set(identities_in_cm) - set(identities_to_ignore)

    if identities_in_cm_set != set(identities_in_crd):
        # Raise exception to make the monitoring probe fail
        raise Exception("monitoring check result : out-of-sync")

    return True


def deploy_crd_definition() -> None:
    """Deploy the CRD (IamIdentityMapping) located in kubernetes/."""
    crd_file_path = get_project_root() / "kubernetes" / "iamidentitymappings.yaml"
    with open(crd_file_path.resolve(), "r") as stream:
        body = yaml.safe_load(stream)
    extensions_api = client.ApiextensionsV1Api()
    crds = extensions_api.list_custom_resource_definition()
    crds_name = {x["metadata"]["name"]: x["metadata"]["resource_version"] for x in crds.to_dict()["items"]}
    crd_name = body["metadata"]["name"]
    if crd_name not in crds_name.keys():
        try:
            extensions_api.create_custom_resource_definition(body)
        except ValueError as err:
            if err.args[0] != "Invalid value for `conditions`, must not be `None`":
                raise err
    else:
        body["metadata"]["resourceVersion"] = crds_name[crd_name]
        extensions_api.replace_custom_resource_definition(crd_name, body)


def full_synchronize() -> None:
    """Synchronize all aws-auth configmap mappings with existing IamIdentityMappings.

    Important note: This method will ignore any existing entries in mapUsers and mapRoles.
                    As long as they satisfy the CRD, they will be left unchanged in
                    the aws-auth configmap.
    """
    # Get Kubernetes" objects
    configmap = API.read_namespaced_config_map("aws-auth", "kube-system")
    identity_mappings = custom_objects_API.list_cluster_custom_object(GROUP, VERSION, PLURAL)

    cm_identities = get_cm_identity_mappings(configmap)
    cm_identities = cm_identities if isinstance(cm_identities, list) else list()

    for identity_mapping in identity_mappings["items"]:
        cm_identities = ensure_identity(identity_mapping["spec"], cm_identities)

    asyncio.run(apply_cm_identity_mappings(configmap, cm_identities))


def get_cm_identity_mappings(configmap: V1ConfigMap) -> list:
    """Get the identity mappings from the aws-auth configmap as a list.

    :return identities: The combined user and role mapping list
    """
    try:
        identities = []
        if configmap.data.get("mapUsers"):
            identities.extend(yaml.safe_load(configmap.data.get("mapUsers")))
        if configmap.data.get("mapRoles"):
            identities.extend(yaml.safe_load(configmap.data.get("mapRoles")))

        return identities
    except yaml.YAMLError as yaml_error:
        logger.warning("Operator quitting. Error loading configmap mappings. : %s", yaml_error)
        raise yaml_error


async def apply_cm_identity_mappings(existing_cm: V1ConfigMap, identity_mappings: list) -> None:
    """Apply new identity mappings to override the existing aws-auth mapping.

    :param existing_cm: The current configmap
    :param identity_mappings: The new identity mappings
    """
    user_mappings = []
    role_mappings = []
    for identity_mapping in identity_mappings:
        if identity_mapping.get("userarn") is not None:
            user_mappings.append(identity_mapping)
        elif identity_mapping.get("rolearn") is not None:
            role_mappings.append(identity_mapping)
        else:
            logger.warning("Unrecognized mapping. Cannot map %s. Removing non compliant mapping.", identity_mapping)

    existing_cm.data["mapUsers"] = yaml.safe_dump(user_mappings)
    existing_cm.data["mapRoles"] = yaml.safe_dump(role_mappings)
    API.patch_namespaced_config_map("aws-auth", "kube-system", existing_cm)


def ensure_identity(identity: dict, identity_list: list) -> list:
    """Ensure the identity is in the list and update it if it is, add the identity if not present.

    :param identity: The identity to check
    :param identity_list: The list to check against
    :return list: The updated list
    """

    for i, existing_identity in enumerate(identity_list):
        # Handle existing identity
        if existing_identity["username"] == identity["username"]:
            identity_list[i] = identity
            return identity_list
    # Handle new identity
    identity_list.append(identity)
    return identity_list


def delete_identity(identity: dict, identity_list: list) -> list:
    """Delete an identity from the identity list if present.

    :param identity: The identity to delete
    :param identity_list: The list of identities
    :return list: The updated list
    """

    for i, existing_user in enumerate(identity_list):
        if existing_user["username"] == identity["username"]:
            del identity_list[i]
            return identity_list

    logger.warning("Failed to delete %s, identity was not found", identity["username"])
    return identity_list


def get_project_root() -> Path:
    """Return the root folder.

    If this file is moved, this relative path NEEDS to be changed accordingly.

    :return path: The path object at the root of the project
    """
    path = Path(__file__)
    return path.parent.parent.parent
