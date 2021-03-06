# -*- coding: utf-8 -*-
'''
Module for handling openstack keystone calls.

:optdepends:    - keystoneclient Python adapter
:configuration: This module is not usable until the following are specified
    either in a pillar or in the minion's config file:

    .. code-block:: yaml

        keystone.user: admin
        keystone.password: verybadpass
        keystone.project: admin
        keystone.project_id: f80919baedab48ec8931f200c65a50df
        keystone.auth_url: 'http://127.0.0.1:5000/v2.0/'

    OR (for token based authentication)

    .. code-block:: yaml

        keystone.token: 'ADMIN'
        keystone.endpoint: 'http://127.0.0.1:35357/v2.0'

    If configuration for multiple openstack accounts is required, they can be
    set up as different configuration profiles. For example:

    .. code-block:: yaml

        openstack1:
          keystone.user: admin
          keystone.password: verybadpass
          keystone.project: admin
          keystone.project_id: f80919baedab48ec8931f200c65a50df
          keystone.auth_url: 'http://127.0.0.1:5000/v2.0/'

        openstack2:
          keystone.user: admin
          keystone.password: verybadpass
          keystone.project: admin
          keystone.project_id: f80919baedab48ec8931f200c65a50df
          keystone.auth_url: 'http://127.0.0.2:5000/v2.0/'

    With this configuration in place, any of the keystone functions can make use
    of a configuration profile by declaring it explicitly.
    For example:

    .. code-block:: bash

        salt '*' keystone.project_list profile=openstack1
'''

# Import Python libs
from __future__ import absolute_import
import logging

# Import Salt Libs
import salt.ext.six as six

# Import third party libs
HAS_KEYSTONE = False
try:
    # pylint: disable=import-error
    from keystoneclient.v3 import client
    import keystoneclient.exceptions
    # pylint: enable=import-error
    HAS_KEYSTONE = True
except ImportError:
    pass

log = logging.getLogger(__name__)


def __virtual__():
    '''
    Only load this module if keystone
    is installed on this minion.
    '''
    if HAS_KEYSTONE:
        return 'keystone'
    return False

__opts__ = {}


def auth(profile=None, **connection_args):
    '''
    Set up keystone credentials. Only intended to be used within Keystone-enabled modules.

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.auth
    '''

    if profile:
        prefix = profile + ":keystone."
    else:
        prefix = "keystone."

    # look in connection_args first, then default to config file
    def get(key, default=None):
        return connection_args.get('connection_' + key,
            __salt__['config.get'](prefix + key, default))

    user = get('user', 'admin')
    password = get('password', 'ADMIN')
    project = get('project', 'admin')
    project_id = get('project_id')
    auth_url = get('auth_url', 'http://127.0.0.1:35357/v2.0/')
    insecure = get('insecure', False)
    token = get('token')
    endpoint = get('endpoint', 'http://127.0.0.1:35357/v2.0')

    if token:
        kwargs = {'token': token,
                  'endpoint': endpoint}
    else:
        kwargs = {'username': user,
                  'password': password,
                  'project_name': project,
                  'project_id': project_id,
                  'auth_url': auth_url}
        # 'insecure' keyword not supported by all v2.0 keystone clients
        #   this ensures it's only passed in when defined
        if insecure:
            kwargs['insecure'] = True

    return client.Client(**kwargs)


def ec2_credentials_create(user_id=None, name=None,
                           project_id=None, project=None,
                           profile=None, **connection_args):
    '''
    Create EC2-compatible credentials for user per project

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.ec2_credentials_create name=admin project=admin
        salt '*' keystone.ec2_credentials_create \
user_id=c965f79c4f864eaaa9c3b41904e67082 \
project_id=722787eb540849158668370dc627ec5f
    '''
    kstone = auth(profile, **connection_args)

    if name:
        user_id = user_get(name=name, profile=profile,
                           **connection_args)[name]['id']
    if not user_id:
        return {'Error': 'Could not resolve User ID'}

    if project:
        project_id = project_get(name=project, profile=profile,
                               **connection_args)[project]['id']
    if not project_id:
        return {'Error': 'Could not resolve Tenant ID'}

    newec2 = kstone.ec2.create(user_id, project_id)
    return {'access': newec2.access,
            'secret': newec2.secret,
            'project_id': newec2.project_id,
            'user_id': newec2.user_id}


def ec2_credentials_delete(user_id=None, name=None, access_key=None,
                           profile=None, **connection_args):
    '''
    Delete EC2-compatible credentials

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.ec2_credentials_delete \
860f8c2c38ca4fab989f9bc56a061a64 access_key=5f66d2f24f604b8bb9cd28886106f442
        salt '*' keystone.ec2_credentials_delete name=admin \
access_key=5f66d2f24f604b8bb9cd28886106f442
    '''
    kstone = auth(profile, **connection_args)

    if name:
        user_id = user_get(name=name, profile=None, **connection_args)[name]['id']
    if not user_id:
        return {'Error': 'Could not resolve User ID'}
    kstone.ec2.delete(user_id, access_key)
    return 'ec2 key "{0}" deleted under user id "{1}"'.format(access_key,
                                                              user_id)


def ec2_credentials_get(user_id=None, name=None, access=None,
                        profile=None, **connection_args):
    '''
    Return ec2_credentials for a user (keystone ec2-credentials-get)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.ec2_credentials_get c965f79c4f864eaaa9c3b41904e67082 access=722787eb540849158668370dc627ec5f
        salt '*' keystone.ec2_credentials_get user_id=c965f79c4f864eaaa9c3b41904e67082 access=722787eb540849158668370dc627ec5f
        salt '*' keystone.ec2_credentials_get name=nova access=722787eb540849158668370dc627ec5f
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for user in kstone.users.list():
            if user.name == name:
                user_id = user.id
                break
    if not user_id:
        return {'Error': 'Unable to resolve user id'}
    if not access:
        return {'Error': 'Access key is required'}
    ec2_credentials = kstone.ec2.get(user_id=user_id, access=access,
                                     profile=profile, **connection_args)
    ret[ec2_credentials.user_id] = {'user_id': ec2_credentials.user_id,
                                    'project': ec2_credentials.project_id,
                                    'access': ec2_credentials.access,
                                    'secret': ec2_credentials.secret}
    return ret


def ec2_credentials_list(user_id=None, name=None, profile=None,
                         **connection_args):
    '''
    Return a list of ec2_credentials for a specific user (keystone ec2-credentials-list)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.ec2_credentials_list 298ce377245c4ec9b70e1c639c89e654
        salt '*' keystone.ec2_credentials_list user_id=298ce377245c4ec9b70e1c639c89e654
        salt '*' keystone.ec2_credentials_list name=jack
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for user in kstone.users.list():
            if user.name == name:
                user_id = user.id
                break
    if not user_id:
        return {'Error': 'Unable to resolve user id'}
    for ec2_credential in kstone.ec2.list(user_id):
        ret[ec2_credential.user_id] = {'user_id': ec2_credential.user_id,
                                       'project_id': ec2_credential.project_id,
                                       'access': ec2_credential.access,
                                       'secret': ec2_credential.secret}
    return ret


def endpoint_get(service, profile=None, **connection_args):
    '''
    Return a specific endpoint (keystone endpoint-get)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.endpoint_get nova
    '''
    kstone = auth(profile, **connection_args)
    services = service_list(profile, **connection_args)
    if service not in services:
        return {'Error': 'Could not find the specified service'}
    service_id = services[service]['id']
    endpoints = endpoint_list(profile, **connection_args)
    for endpoint in endpoints:
        if endpoints[endpoint]['service_id'] == service_id:
            return endpoints[endpoint]
    return {'Error': 'Could not find endpoint for the specified service'}


def endpoint_list(profile=None, **connection_args):
    '''
    Return a list of available endpoints (keystone endpoints-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.endpoint_list
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    for endpoint in kstone.endpoints.list():
        ret[endpoint.id] = {'id': endpoint.id,
                            'region': endpoint.region,
                            'interface': endpoint.interface,
                            'url': endpoint.url,
                            'service_id': endpoint.service_id}
    return ret


def endpoint_create(service, publicurl=None, internalurl=None, adminurl=None,
                    region=None, profile=None, **connection_args):
    '''
    Create an endpoint for an Openstack service

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.endpoint_create nova 'http://public/url'
            'http://internal/url' 'http://adminurl/url' region
    '''
    kstone = auth(profile, **connection_args)
    keystone_service = service_get(name=service, profile=profile,
                                   **connection_args)
    if not keystone_service or 'Error' in keystone_service:
        return {'Error': 'Could not find the specified service'}
    ep = endpoint_get(service, profile, **connection_args)
    for interface, url in {'public': publicurl, 'admin': adminurl, 'internal': internalurl}.iteritems():
        kstone.endpoints.create(keystone_service[service]['id'], url, interface=interface, region=region)
    return endpoint_get(service, profile, **connection_args)


def endpoint_delete(service, profile=None, **connection_args):
    '''
    Delete endpoints of an Openstack service

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.endpoint_delete nova
    '''
    kstone = auth(profile, **connection_args)
    services = service_list(profile, **connection_args)
    if service not in services:
        return {'Error': 'Could not find the specified service'}
    service_id = services[service]['id']
    endpoints = endpoint_list(profile, **connection_args)
    for _, endpoint in endpoints.iteritems():
        if endpoint['service_id'] == service_id:
            kstone.endpoints.delete(endpoint['id'])
    endpoint = endpoint_get(service, profile, **connection_args)
    if not endpoint or 'Error' in endpoint:
        return True


def role_create(name, profile=None, **connection_args):
    '''
    Create a named role.

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.role_create admin
    '''

    kstone = auth(profile, **connection_args)
    if 'Error' not in role_get(name=name, profile=profile, **connection_args):
        return {'Error': 'Role "{0}" already exists'.format(name)}
    role = kstone.roles.create(name)
    return role_get(name=name, profile=profile, **connection_args)


def role_delete(role_id=None, name=None, profile=None,
                **connection_args):
    '''
    Delete a role (keystone role-delete)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.role_delete c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.role_delete role_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.role_delete name=admin
    '''
    kstone = auth(profile, **connection_args)

    if name:
        for role in kstone.roles.list():
            if role.name == name:
                role_id = role.id
                break
    if not role_id:
        return {'Error': 'Unable to resolve role id'}
    role = role_get(role_id, profile=profile, **connection_args)
    kstone.roles.delete(role)
    ret = 'Role ID {0} deleted'.format(role_id)
    if name:
        ret += ' ({0})'.format(name)
    return ret


def role_get(role_id=None, name=None, profile=None, **connection_args):
    '''
    Return a specific roles (keystone role-get)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.role_get c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.role_get role_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.role_get name=nova
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for role in kstone.roles.list():
            if role.name == name:
                role_id = role.id
                break
    if not role_id:
        return {'Error': 'Unable to resolve role id'}
    role = kstone.roles.get(role_id)
    ret[role.name] = {'id': role.id,
                      'name': role.name}
    return ret


def role_list(profile=None, **connection_args):
    '''
    Return a list of available roles (keystone role-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.role_list
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    for role in kstone.roles.list():
        ret[role.name] = {'id': role.id,
                          'name': role.name}
    return ret


def service_create(name, service_type, description=None, profile=None,
                   **connection_args):
    '''
    Add service to Keystone service catalog

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.service_create nova compute \
'OpenStack Compute Service'
    '''
    kstone = auth(profile, **connection_args)
    service = kstone.services.create(name, service_type, description)
    return service_get(service.id, profile=profile, **connection_args)


def service_delete(service_id=None, name=None, profile=None, **connection_args):
    '''
    Delete a service from Keystone service catalog

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.service_delete c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.service_delete name=nova
    '''
    kstone = auth(profile, **connection_args)
    if name:
        service_id = service_get(name=name, profile=profile,
                                 **connection_args)[name]['id']
    service = kstone.services.delete(service_id)
    return 'Keystone service ID "{0}" deleted'.format(service_id)


def service_get(service_id=None, name=None, profile=None, **connection_args):
    '''
    Return a specific services (keystone service-get)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.service_get c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.service_get service_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.service_get name=nova
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for service in kstone.services.list():
            if service.name == name:
                service_id = service.id
                break
    if not service_id:
        return {'Error': 'Unable to resolve service id'}
    service = kstone.services.get(service_id)
    ret[service.name] = {'id': service.id,
                         'name': service.name,
                         'type': service.type,
                         'description': service.description}
    return ret


def service_list(profile=None, **connection_args):
    '''
    Return a list of available services (keystone services-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.service_list
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    for service in kstone.services.list():
        ret[service.name] = {'id': service.id,
                             'name': service.name,
                             'description': service.description,
                             'type': service.type}
    return ret


def project_create(name, description=None, enabled=True, domain=None,
                   profile=None, **connection_args):
    '''
    Create a keystone project

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.project_create nova description='nova project'
        salt '*' keystone.project_create test enabled=False
    '''
    kstone = auth(profile, **connection_args)
    new = kstone.projects.create(name, description=description, domain=domain,
                                 enabled=enabled)
    return project_get(new.id, profile=profile, **connection_args)


def project_delete(project_id=None, name=None, profile=None, **connection_args):
    '''
    Delete a project (keystone project-delete)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.project_delete c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.project_delete project_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.project_delete name=demo
    '''
    kstone = auth(profile, **connection_args)
    if name:
        for project in kstone.projects.list():
            if project.name == name:
                project_id = project.id
                break
    if not project_id:
        return {'Error': 'Unable to resolve project id'}
    kstone.projects.delete(project_id)
    ret = 'Tenant ID {0} deleted'.format(project_id)
    if name:

        ret += ' ({0})'.format(name)
    return ret


def project_get(project_id=None, name=None, profile=None, domain=None,
                **connection_args):
    '''
    Return a specific projects (keystone project-get)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.project_get c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.project_get project_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.project_get name=nova
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for project in kstone.projects.list(domain=domain):
            if project.name == name:
                project_id = project.id
                break
    if not project_id:
        return {'Error': 'Unable to resolve project id'}
    project = kstone.projects.get(project_id)
    ret[project.name] = {'id': project.id,
                         'name': project.name,
                         'description': project.description,
                         'enabled': project.enabled}
    return ret


def project_list(domain=None, profile=None, **connection_args):
    '''
    Return a list of available projects (keystone projects-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.project_list
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    for project in kstone.projects.list(domain=domain):
        ret[project.name] = {'id': project.id,
                            'name': project.name,
                            'description': project.description,
                            'enabled': project.enabled}
    return ret


def project_update(project_id=None, name=None, description=None,
                   domain=None, enabled=None, profile=None,
                   **connection_args):
    '''
    Update a project's information (keystone project-update)
    The following fields may be updated: name, email, enabled.
    Can only update name if targeting by ID

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.project_update name=admin enabled=True
        salt '*' keystone.project_update c965f79c4f864eaaa9c3b41904e67082 name=admin email=admin@domain.com
    '''
    kstone = auth(profile, **connection_args)
    if not project_id:
        for project in kstone.projects.list():
            if project.name == name:
                project_id = project.id
                break
    if not project_id:
        return {'Error': 'Unable to resolve project id'}

    project = kstone.projects.get(project_id)
    if not name:
        name = project.name
    if not description:
        description = project.description
    if enabled is None:
        enabled = project.enabled
    kstone.projects.update(project_id, name=name, domain=domain,
                           description=description, enabled=enabled)


def token_get(profile=None, **connection_args):
    '''
    Return the configured tokens (keystone token-get)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.token_get c965f79c4f864eaaa9c3b41904e67082
    '''
    kstone = auth(profile, **connection_args)
    token = kstone.service_catalog.get_token()
    return {'id': token['id'],
            'expires': token['expires'],
            'user_id': token['user_id'],
            'project_id': token['project_id']}


def user_list(default_project=None, domain=None,
              profile=None, **connection_args):
    '''
    Return a list of available users (keystone user-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.user_list
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    for user in kstone.users.list(default_project=default_project,
                                  domain=domain):
        ret[user.name] = {'id': user.id,
                          'name': user.name,
                          'email': user.email,
                          'enabled': user.enabled}
        project_id = getattr(user, 'projectId', None)
        if project_id:
            ret[user.name]['project_id'] = project_id
    return ret


def user_get(user_id=None, name=None, domain=None,
             profile=None, **connection_args):
    '''
    Return a specific users (keystone user-get)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_get c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.user_get user_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.user_get name=nova
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if name:
        for user in kstone.users.list(domain=domain):
            if user.name == name:
                user_id = user.id
                break
    if not user_id:
        return {'Error': 'Unable to resolve user id'}
    try:
        user = kstone.users.get(user_id)
    except keystoneclient.exceptions.NotFound:
        msg = 'Could not find user \'{0}\''.format(user_id)
        log.error(msg)
        return {'Error': msg}

    ret[user.name] = {'id': user.id,
                      'name': user.name,
                      'email': user.email,
                      'enabled': user.enabled}
    project_id = getattr(user, 'projectId', None)
    if project_id:
        ret[user.name]['project_id'] = project_id
    return ret


def user_create(name, password, email, project_id=None, domain=None,
                enabled=True, profile=None, **connection_args):
    '''
    Create a user (keystone user-create)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_create name=jack password=zero email=jack@halloweentown.org project_id=a28a7b5a999a455f84b1f5210264375e enabled=True
    '''
    kstone = auth(profile, **connection_args)
    item = kstone.users.create(name=name,
                               password=password,
                               email=email,
                               domain=None,
                               project_id=project_id,
                               enabled=enabled)
    return user_get(item.id, profile=profile, **connection_args)


def user_delete(user_id=None, name=None, profile=None, **connection_args):
    '''
    Delete a user (keystone user-delete)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_delete c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.user_delete user_id=c965f79c4f864eaaa9c3b41904e67082
        salt '*' keystone.user_delete name=nova
    '''
    kstone = auth(profile, **connection_args)
    if name:
        for user in kstone.users.list():
            if user.name == name:
                user_id = user.id
                break
    if not user_id:
        return {'Error': 'Unable to resolve user id'}
    kstone.users.delete(user_id)
    ret = 'User ID {0} deleted'.format(user_id)
    if name:

        ret += ' ({0})'.format(name)
    return ret


def user_update(user_id=None, name=None, email=None, password=None,
                enabled=None, domain=None, project=None, profile=None,
                **connection_args):
    '''
    Update a user's information (keystone user-update)
    The following fields may be updated: name, email, enabled, project.
    Because the name is one of the fields, a valid user id is required.

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_update user_id=c965f79c4f864eaaa9c3b41904e67082 name=newname
        salt '*' keystone.user_update c965f79c4f864eaaa9c3b41904e67082 name=newname email=newemail@domain.com
    '''
    kstone = auth(profile, **connection_args)
    if not user_id:
        for user in kstone.users.list(domain=domain):
            if user.name == name:
                user_id = user.id
                break
        if not user_id:
            return {'Error': 'Unable to resolve user id'}
    user = kstone.users.get(user_id)
    # Keep previous settings if not updating them
    if not name:
        name = user.name
    if not email:
        email = user.email
    if enabled is None:
        enabled = user.enabled
    kstone.users.update(user=user_id, name=name, email=email,
                        password=password, domain=domain,
                        default_project=project, enabled=enabled)
    ret = 'Info updated for user ID {0}'.format(user_id)
    return ret


def user_role_add(user_id=None, user=None, project_id=None,
                  project=None, role_id=None, role=None, profile=None,
                  **connection_args):
    '''
    Add role for user in project (keystone user-role-add)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_role_add \
user_id=298ce377245c4ec9b70e1c639c89e654 \
project_id=7167a092ece84bae8cead4bf9d15bb3b \
role_id=ce377245c4ec9b70e1c639c89e8cead4
        salt '*' keystone.user_role_add user=admin project=admin role=admin
    '''
    kstone = auth(profile, **connection_args)
    if user:
        user_id = user_get(name=user, profile=profile,
                           **connection_args)[user]['id']
    else:
        user = next(six.iterkeys(user_get(user_id, profile=profile,
                                          **connection_args)))['name']
    if not user_id:
        return {'Error': 'Unable to resolve user id'}

    if project:
        project_id = project_get(name=project, profile=profile,
                               **connection_args)[project]['id']
    else:
        project = next(six.iterkeys(project_get(project_id, profile=profile,
                                              **connection_args)))['name']
    if not project_id:
        return {'Error': 'Unable to resolve project id'}

    if role:
        role_id = role_get(name=role, profile=profile,
                           **connection_args)[role]['id']
    else:
        role = next(six.iterkeys(role_get(role_id, profile=profile,
                                          **connection_args)))['name']
    if not role_id:
        return {'Error': 'Unable to resolve role id'}

    kstone.roles.grant(role_id, user=user_id, project=project_id)
    ret_msg = '"{0}" role added for user "{1}" for "{2}" project'
    return ret_msg.format(role, user, project)


def user_role_remove(user_id=None, user=None, project_id=None,
                     project=None, role_id=None, role=None,
                     profile=None, **connection_args):
    '''
    Remove role for user in project (keystone user-role-remove)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_role_remove \
user_id=298ce377245c4ec9b70e1c639c89e654 \
project_id=7167a092ece84bae8cead4bf9d15bb3b \
role_id=ce377245c4ec9b70e1c639c89e8cead4
        salt '*' keystone.user_role_remove user=admin project=admin role=admin
    '''
    kstone = auth(profile, **connection_args)
    if user:
        user_id = user_get(name=user, profile=profile,
                           **connection_args)[user]['id']
    else:
        user = next(six.iterkeys(user_get(user_id, profile=profile,
                                          **connection_args)))['name']
    if not user_id:
        return {'Error': 'Unable to resolve user id'}

    if project:
        project_id = project_get(name=project, profile=profile,
                               **connection_args)[project]['id']
    else:
        project = next(six.iterkeys(project_get(project_id, profile=profile,
                                              **connection_args)))['name']
    if not project_id:
        return {'Error': 'Unable to resolve project id'}

    if role:
        role_id = role_get(name=role, profile=profile,
                           **connection_args)[role]['id']
    else:
        role = next(six.iterkeys(role_get(role_id)))['name']
    if not role_id:
        return {'Error': 'Unable to resolve role id'}

    kstone.roles.revoke(role=role_id, user=user_id, project=project_id)
    ret_msg = '"{0}" role removed for user "{1}" under "{2}" project'
    return ret_msg.format(role, user, project)


def user_role_list(user_id=None, project_id=None, user_name=None,
                   project_name=None, profile=None, **connection_args):
    '''
    Return a list of available user_roles (keystone user-roles-list)

    CLI Examples:

    .. code-block:: bash

        salt '*' keystone.user_role_list \
user_id=298ce377245c4ec9b70e1c639c89e654 \
project_id=7167a092ece84bae8cead4bf9d15bb3b
        salt '*' keystone.user_role_list user_name=admin project_name=admin
    '''
    kstone = auth(profile, **connection_args)
    ret = {}
    if user_name:
        for user in kstone.users.list():
            if user.name == user_name:
                user_id = user.id
                break
    if project_name:
        for project in kstone.projects.list():
            if project.name == project_name:
                project_id = project.id
                break
    if not user_id or not project_id:
        return {'Error': 'Unable to resolve user or project id'}
    for role in kstone.roles.list(user=user_id, project=project_id):
        ret[role.name] = {'id': role.id,
                          'name': role.name,
                          'user_id': user_id,
                          'project_id': project_id}
    return ret


def _item_list(profile=None, **connection_args):
    '''
    Template for writing list functions
    Return a list of available items (keystone items-list)

    CLI Example:

    .. code-block:: bash

        salt '*' keystone.item_list
    '''
    kstone = auth(profile, **connection_args)
    ret = []
    for item in kstone.items.list():
        ret.append(item.__dict__)
        #ret[item.name] = {
        #        'id': item.id,
        #        'name': item.name,
        #        }
    return ret

    # The following is a list of functions that need to be incorporated in the
    # keystone module. This list should be updated as functions are added.
    #
    # endpoint-create     Create a new endpoint associated with a service
    # endpoint-delete     Delete a service endpoint
    # discover            Discover Keystone servers and show authentication
    #                     protocols and
    # bootstrap           Grants a new role to a new user on a new project, after
    #                     creating each.
