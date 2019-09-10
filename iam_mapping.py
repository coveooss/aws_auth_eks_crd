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
    logger.info("Could not load kubeconfig. Error is : {}".format(e.message))

API = client.CoreV1Api()


@kopf.on.create('iamauthenticator.k8s.aws', 'v1alpha1', 'iamidentitymappings')
def create_mapping(body: dict, meta: dict, spec: dict, **kwargs):
    logger.info('Adding mapping for user {} as {} to {}'.format(
        spec['arn'], spec['username'], spec['groups']))

    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    users = get_user_mapping(cm)
    updated_mapping = ensure_user(spec, users)
    apply_mapping(cm, updated_mapping)


@kopf.on.update('iamauthenticator.k8s.aws', 'v1alpha1', 'iamidentitymappings')
def update_mapping(body: dict, meta: dict, spec: dict, **kwargs):
    logger.info('Update mapping for user {} as {} to {}'.format(
        spec['arn'], spec['username'], spec['groups']))

    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    users = get_user_mapping(cm)
    updated_mapping = ensure_user(spec, users)
    apply_mapping(cm, updated_mapping)


@kopf.on.delete('iamauthenticator.k8s.aws', 'v1alpha1', 'iamidentitymappings')
def delete_mapping(body: dict, meta: dict, spec: dict, **kwargs):
    logger.info('Delete mapping for user {} as {} to {}'.format(
        spec['arn'], spec['username'], spec['groups']))

    cm = API.read_namespaced_config_map('aws-auth', 'kube-system')
    users = get_user_mapping(cm)
    updated_mapping = delete_user(spec, users)
    apply_mapping(cm, updated_mapping)


def get_user_mapping(cm):
    if 'mapUsers' in cm.data:
        return yaml.safe_load(cm.data['mapUsers'])
    else:
        return []


def apply_mapping(existing_cm, user_mapping):
    existing_cm.data["mapUsers"] = yaml.dump(user_mapping)
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
