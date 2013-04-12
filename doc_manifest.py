#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2012, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#

import os
import time
import yaml
from repo_structure import get_repo_manifests


def write_stack_manifest(output_dir, stack_name, manifest,
                         vcs_type, vcs_uri, api_homepage,
                         packages, tags_db, repo_name, doc_job,
                         version):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    m_yaml = {}
    m_yaml['api_documentation'] = api_homepage
    m_yaml['vcs'] = vcs_type
    m_yaml['vcs_uri'] = vcs_uri

    m_yaml['authors'] = manifest.author or ''
    m_yaml['brief'] = manifest.brief or ''
    m_yaml['depends'] = [dep.name for dep in manifest.depends] or ''
    m_yaml['packages'] = packages or ''
    m_yaml['description'] = manifest.description or ''
    m_yaml['license'] = manifest.license or ''
    m_yaml['msgs'] = []
    m_yaml['srvs'] = []
    m_yaml['url'] = manifest.url or ''
    m_yaml['package_type'] = 'stack'
    m_yaml['repo_name'] = repo_name
    m_yaml['doc_job'] = doc_job
    m_yaml['timestamp'] = time.time()
    m_yaml['vcs_version'] = version

    m_yaml['depends_on'] = []
    if tags_db.has_reverse_deps(stack_name):
        m_yaml['depends_on'] = tags_db.get_reverse_deps(stack_name)

    #Update our dependency list
    if 'depends' in m_yaml and type(m_yaml['depends']) == list:
        tags_db.add_forward_deps(stack_name, m_yaml['depends'])

    #Make sure to write stack dependencies to the tags db
    tags_db.set_metapackage_deps(stack_name, packages)

    with open(os.path.join(output_dir, 'manifest.yaml'), 'w+') as f:
        yaml.safe_dump(m_yaml, f, default_flow_style=False)


def write_distro_specific_manifest(manifest_file, package, vcs_type,
                                   vcs_uri, api_homepage, tags_db,
                                   repo_name, doc_job, version):
    m_yaml = {}
    if os.path.isfile(manifest_file):
        with open(manifest_file, 'r') as f:
            m_yaml = yaml.load(f)

    m_yaml['api_documentation'] = api_homepage
    m_yaml['vcs'] = vcs_type
    m_yaml['vcs_uri'] = vcs_uri
    m_yaml['repo_name'] = repo_name
    m_yaml['doc_job'] = doc_job
    m_yaml['timestamp'] = time.time()
    m_yaml['vcs_version'] = version

    m_yaml['depends_on'] = []
    if tags_db.has_reverse_deps(package):
        m_yaml['depends_on'] = tags_db.get_reverse_deps(package)

    if not os.path.isdir(os.path.dirname(manifest_file)):
        os.makedirs(os.path.dirname(manifest_file))

    #Update our dependency list
    if 'depends' in m_yaml and type(m_yaml['depends']) == list:
        tags_db.add_forward_deps(package, m_yaml['depends'])

    #We need to keep track of metapackages separately as they're special kinds
    #of reverse deps
    if 'package_type' in m_yaml and m_yaml['package_type'] == 'metapackage':
        m_yaml['packages'] = m_yaml['depends']
        tags_db.set_metapackage_deps(package, m_yaml['depends'])

    #Check to see if this package is part of any metapackages
    if tags_db.has_metapackages(package):
        m_yaml['metapackages'] = tags_db.get_metapackages(package)

    with open(manifest_file, 'w+') as f:
        yaml.safe_dump(m_yaml, f, default_flow_style=False)


def write_stack_manifests(stacks, docspace, ros_distro, repo_map, tags_db, doc_job, homepage):
    #Write stack manifest files for all stacks, we can just do this off the
    #stack.xml files
    for stack, path in stacks.iteritems():
        import rospkg
        #Get the dependencies of a dry stack from the stack.xml
        stack_manifest = rospkg.parse_manifest_file(path, rospkg.STACK_FILE)
        stack_packages = get_repo_manifests(path, manifest='package').keys()
        stack_relative_doc_path = "%s/doc/%s/api/%s" % (docspace, ros_distro, stack)
        stack_doc_path = os.path.abspath(stack_relative_doc_path)
        write_stack_manifest(stack_doc_path, stack, stack_manifest, repo_map[stack]['type'], repo_map[stack]['url'], "%s/%s/api/%s/html" % (homepage, ros_distro, stack), stack_packages, tags_db, repo_map[stack]['name'], doc_job, repo_map[stack]['version'])
