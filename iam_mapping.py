import kopf
import yaml
import copy
import logging
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger('operator')

try:
    config.load_kube_config('./kubeconfig')
except Exception as e:
    logger.info("Could not load kubeconfig. Error is : {}".format(e))

API = client.CoreV1Api()
custom_objects_API = client.CustomObjectsApi()
GROUP = 'iamauthenticator.k8s.aws'
VERSION = 'v1alpha1'
PLURAL = 'iamidentitymappings'


@kopf.on.update(GROUP, VERSION, PLURAL)
@kopf.on.create(GROUP, VERSION, PLURAL)
async def create_mapping(body: dict, meta: dict, spec: dict, event: str, diff: set, **kwargs):
    # Do nothing when we have no diff
    if len(diff) < 1:
        return dict()

    logger.info('{} mapping for user {} as {} to {}'.format(
        event.title(), spec['userarn'], spec['username'], spec['groups']))

    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    users = get_user_mapping(cm)
    updated_mapping = ensure_user(spec, users)
    apply_mapping(cm, updated_mapping)


@kopf.on.delete(GROUP, VERSION, PLURAL)
def delete_mapping(body: dict, meta: dict, spec: dict, **kwargs):
    logger.info('Delete mapping for user {} as {} to {}'.format(
        spec['userarn'], spec['username'], spec['groups']))

    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    users = get_user_mapping(cm)
    updated_mapping = delete_user(spec, users)
    apply_mapping(cm, updated_mapping)


def deploy_crd_definition():
    with open("kubernetes/iamidentitymappings.yaml", 'r') as stream:
        try:
            body = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error(exc)
            exit(1)
    extensions_api = client.ApiextensionsV1beta1Api()
    crds = extensions_api.list_custom_resource_definition()
    crds_name = [x['metadata']['name'] for x in crds.to_dict()['items']]
    if body["metadata"]["name"] not in crds_name:
        try:
            extensions_api.create_custom_resource_definition(body)
        except ValueError as err:
            if not err.args[0] == 'Invalid value for `conditions`, must not be `None`':
                raise err


def full_synchronize():
    # Get Kubernetes' objects
    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    identity_mappings = custom_objects_API.list_cluster_custom_object(
        GROUP, VERSION, PLURAL)

    users = get_user_mapping(cm)
    users = users if type(users) == "list" else list()
    for im in identity_mappings["items"]:
        users = ensure_user(im["spec"], users)
    apply_mapping(cm, users)


def get_user_mapping(cm):
    try:
        return yaml.safe_load(cm.data['mapUsers'])
    except:
        return []


def apply_mapping(existing_cm, user_mapping):
    existing_cm.data["mapUsers"] = yaml.safe_dump(user_mapping)
    API.patch_namespaced_config_map('aws-auth', 'kube-system', existing_cm)


def ensure_user(user, user_list):
    for i, existing_user in enumerate(user_list):
        # Handle existing user
        if existing_user['username'] == user['username']:
            user_list[i] = user
            return user_list
    # Handle new user
    else:
        user_list.append(user)
    return user_list


def delete_user(user, user_list):
    for i, existing_user in enumerate(user_list):
        if existing_user['username'] == user['username']:
            del user_list[i]
            return user_list
    else:
        raise Exception(
            "Want to delete {}, but not found".format(user['username']))
    return user_list


# Do a full synchronization at the start
deploy_crd_definition()
full_synchronize()
