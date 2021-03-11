#!/usr/bin/python
# -*- coding: utf-8 -*-

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

"""
(c) 2021, Georg Gadinger <nilsding@nilsding.org>

This file is part of Ansible

Ansible is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Ansible is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a clone of the GNU General Public License
along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
"""

DOCUMENTATION = '''
---
module: one_template
short_description: Manages OpenNebula templates
description:
  - Manages OpenNebula templates
requirements:
  - pyone
options:
  api_url:
    description:
      - URL of the OpenNebula RPC server.
      - It is recommended to use HTTPS so that the username/password are not
      - transferred over the network unencrypted.
      - If not set then the value of the C(ONE_URL) environment variable is used.
    type: str
  api_username:
    description:
      - Name of the user to login into the OpenNebula RPC server. If not set
      - then the value of the C(ONE_USERNAME) environment variable is used.
    type: str
  api_password:
    description:
      - Password of the user to login into OpenNebula RPC server. If not set
      - then the value of the C(ONE_PASSWORD) environment variable is used.
    type: str
  id:
    description:
      - A C(id) of the template you would like to manage.  If not set then a
      - new template will be created with the given C(name).
    type: int
  name:
    description:
      - A C(name) of the template you would like to manage.  If a template with
      - the given name does not exist it will be created, otherwise it will be
      - managed by this module.
    type: str
  template:
    description:
      - The actual template.
    type: str
  state:
    description:
      - C(present) - state that is used to manage the template
      - C(absent) - delete the template
    choices: ["present", "absent"]
    default: present
    type: str
author:
    - "Georg Gadinger (@nilsding)"
'''

EXAMPLES = '''
- name: Fetch the TEMPLATE by id
  community.general.one_template:
    id: 6459
  register: result

- name: Print the TEMPLATE properties
  ansible.builtin.debug:
    var: result

- name: Fetch the TEMPLATE by name
  community.general.one_template:
    name: tf-prd-users-workerredis-p6379a
  register: result

- name: Create a new or update an existing TEMPLATE
  community.general.one_template:
    name: generic-opensuse
    template: |
      CONTEXT = [
        HOSTNAME = "generic-opensuse"
      ]
      CPU = "1"
      CUSTOM_ATTRIBUTE = ""
      DISK = [
        CACHE = "writeback",
        DEV_PREFIX = "sd",
        DISCARD = "unmap",
        IMAGE = "opensuse-leap-15.2",
        IMAGE_UNAME = "oneadmin",
        IO = "threads",
        SIZE = "" ]
      MEMORY = "2048"
      NIC = [
        MODEL = "virtio",
        NETWORK = "testnet",
        NETWORK_UNAME = "oneadmin" ]
      OS = [
        ARCH = "x86_64",
        BOOT = "disk0" ]
      SCHED_REQUIREMENTS = "CLUSTER_ID=\"100\""
      VCPU = "2"

- name: Delete the TEMPLATE by id
  community.general.one_template:
    id: 6459
    state: absent
'''

RETURN = '''
id:
    description: template id
    type: int
    returned: success
    sample: 153
name:
    description: template name
    type: str
    returned: success
    sample: app1
group_id:
    description: template's group id
    type: int
    returned: success
    sample: 1
group_name:
    description: template's group name
    type: str
    returned: success
    sample: one-users
owner_id:
    description: template's owner id
    type: int
    returned: success
    sample: 143
owner_name:
    description: template's owner name
    type: str
    returned: success
    sample: ansible-test
'''

try:
    import pyone
    HAS_PYONE = True
except ImportError:
    HAS_PYONE = False

from ansible.module_utils.basic import AnsibleModule
import os


def get_template(module, client, predicate):
    # -3 means "Resources belonging to the user"
    # the other two parameters are used for pagination, -1 for both essentially means "return all"
    pool = client.templatepool.info(-3, -1, -1)

    for template in pool.VMTEMPLATE:
        if predicate(template):
            return template

    return None


def get_template_by_id(module, client, template_id):
    return get_template(module, client, lambda template: (template.ID == template_id))


def get_template_by_name(module, client, template_name):
    return get_template(module, client, lambda template: (template.NAME == template_name))


def get_template_instance(module, client, requested_id, requested_name):
    if requested_id:
        return get_template_by_id(module, client, requested_id)
    else:
        return get_template_by_name(module, client, requested_name)


def get_template_info(template):
    info = {
        'id': template.ID,
        'name': template.NAME,
        'template': template.TEMPLATE,
        'user_name': template.UNAME,
        'user_id': template.UID,
        'group_name': template.GNAME,
        'group_id': template.GID,
    }

    return info


def create_template(module, client, name, template_data):
    if not module.check_mode:
        client.template.allocate("NAME = \"" + name + "\"\n" + template_data)

    result = get_template_info(get_template_by_name(module, client, name))
    result['changed'] = True

    return result


def update_template(module, client, template, template_data):
    if not module.check_mode:
        # 0 = replace the whole template
        client.template.update(template.ID, template_data, 0)

    result = get_template_info(get_template_by_id(module, client, template.ID))
    # if the previous parsed template data is not equal to the updated one, this has changed
    result['changed'] = template.TEMPLATE != result['template']

    return result


def delete_template(module, client, template):
    if not template:
        return {'changed': False}

    if not module.check_mode:
        client.template.delete(template.ID)

    return {'changed': True}


def get_connection_info(module):
    url = module.params.get('api_url')
    username = module.params.get('api_username')
    password = module.params.get('api_password')

    if not url:
        url = os.environ.get('ONE_URL')

    if not username:
        username = os.environ.get('ONE_USERNAME')

    if not password:
        password = os.environ.get('ONE_PASSWORD')

    if not(url and username and password):
        module.fail_json(msg="One or more connection parameters (api_url, api_username, api_password) were not specified")
    from collections import namedtuple

    auth_params = namedtuple('auth', ('url', 'username', 'password'))

    return auth_params(url=url, username=username, password=password)


def main():
    fields = {
        "api_url": {"required": False, "type": "str"},
        "api_username": {"required": False, "type": "str"},
        "api_password": {"required": False, "type": "str", "no_log": True},
        "id": {"required": False, "type": "int"},
        "name": {"required": False, "type": "str"},
        "state": {
            "default": "present",
            "choices": ["present", "absent"],
            "type": "str"
        },
        "template": {"True": False, "type": "str"},
    }

    module = AnsibleModule(argument_spec=fields,
                           mutually_exclusive=[['id', 'name']],
                           supports_check_mode=True)

    if not HAS_PYONE:
        module.fail_json(msg='This module requires pyone to work!')

    auth = get_connection_info(module)
    params = module.params
    id = params.get('id')
    name = params.get('name')
    state = params.get('state')
    template_data = params.get('template')
    client = pyone.OneServer(auth.url, session=auth.username + ':' + auth.password)

    result = {}

    template = get_template_instance(module, client, id, name)
    needs_creation = False
    if not template and state != 'absent':
        if id:
            module.fail_json(msg="There is no template with id=" + str(id))
        else:
            needs_creation = True

    if state == 'absent':
        result = delete_template(module, client, template)
    else:
        if needs_creation:
            if not template_data:
                module.fail_json(msg="To create a new template, the `template` attribute needs to be set.")

            result = create_template(module, client, name, template_data)
        else:
            if template_data:
                result = update_template(module, client, template, template_data)
            else:
                result = get_template_info(template)
                result['changed'] = False

    module.exit_json(**result)


if __name__ == '__main__':
    main()
