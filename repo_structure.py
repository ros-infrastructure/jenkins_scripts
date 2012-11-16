#!/usr/bin/env python
# Software License Agreement (BSD License)
#
# Copyright (c) 2008, Willow Garage, Inc.
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

import yaml
import urllib2
import os
import sys
from common import append_pymodules_if_needed, BuildException, call

def get_repo_revision(repo_folder, vcs_type):
    #Make sure we're in the right directory
    old_dir = os.getcwd()
    os.chdir(repo_folder)

    if vcs_type == 'git':
        rev = call("git rev-parse HEAD").split('\n')[0]
    elif vcs_type == 'hg':
        rev = call("hg id -i").split('\n')[0]
    elif vcs_type == 'bzr':
        rev = call("bzr revno").split('\n')[0]
    elif vcs_type == 'svn':
        rev = call("svnversion").split('\n')[0]
    else:
        rev = ""
        print >> sys.stderr, "Don't know how to get the version for vcs_type %s, doc generation will always run" % vcs_type

    #Make sure we go back to the original dir
    os.chdir(old_dir)
    return rev

def get_revisions(rosinstall, base_dir):
    revisions = {}
    for item in rosinstall:
        vcs_type = item.keys()[0]
        local_name = item[vcs_type]['local-name']
        path = os.path.join(base_dir, local_name)
        rev = get_repo_revision(path, vcs_type)
        if rev:
            revisions[local_name] = rev
    return revisions

#Check the repos in a rosinstall file for any changes from the last run, update tags_db if necessary
def rev_changes(rosinstall_name, rosinstall, docspace, tags_db):
    changes = False
    last_revisions = tags_db.get_rosinstall_hashes(rosinstall_name) if tags_db.has_rosinstall_hashes(rosinstall_name) else {}
    revisions = get_revisions(rosinstall, docspace)
    if sorted(last_revisions.keys()) == sorted(revisions.keys()):
        for name, rev in last_revisions.iteritems():
            if rev != revisions[name]:
                changes = True
    else:
        changes = True

    #Make sure to update the tags db to the latest list of revisions
    if revisions:
        #Make sure to copy over any information that's not just stored in the repo
        for key, value in last_revisions.iteritems():
            if key not in revisions:
                revisions[key] = value

        tags_db.set_rosinstall_hashes(rosinstall_name, revisions)
    return changes


def get_repo_manifests(repo_folder, manifest='package'):
    append_pymodules_if_needed()
    import rospkg

    manifest_type = rospkg.MANIFEST_FILE

    if manifest == 'stack':
        manifest_type = rospkg.STACK_FILE

    location_cache = {}

    print rospkg.list_by_path(manifest_type, repo_folder, location_cache)

    return location_cache

def get_repo_packages(repo_folder):
    append_pymodules_if_needed()
    from catkin_pkg import packages as catkin_packages

    paths = []

    #find wet packages
    paths.extend([os.path.abspath(os.path.join(repo_folder, pkg_path)) \
                     for pkg_path in catkin_packages.find_package_paths(repo_folder)])

    #Remove any duplicates
    paths = list(set(paths))

    packages = {}
    for path in paths:
        pkg_info = catkin_packages.parse_package(path)
        packages[pkg_info.name] = path

    return packages

def get_repositories_from_rosinstall(rosinstall):
    repos = []
    for item in rosinstall:
        key = item.keys()[0]
        repos.append(item[key]['local-name'])
    return repos

def load_configuration(ros_distro, repo):
    try:
        repo_url = 'https://raw.github.com/ros/rosdistro/master/doc/%s/%s.rosinstall'%(ros_distro, repo)
        f = urllib2.urlopen(repo_url)
        if f.code != 200:
            raise BuildException("Could not find a valid rosinstall file for %s at %s" % (repo, repo_url))
        doc_conf = yaml.load(f.read())
    except (urllib2.URLError, urllib2.HTTPError) as e:
        raise BuildException("Could not find a valid rosinstall file for %s at %s" % (repo, repo_url))

    depends_conf = []
    try:
        depends_repo_url = 'https://raw.github.com/ros/rosdistro/master/doc/%s/%s_depends.rosinstall'%(ros_distro, repo)
        f = urllib2.urlopen(depends_repo_url)
        if f.code == 200:
            print "Found a depends rosinstall file for %s" % repo
            depends_conf = yaml.load(f.read())
    except (urllib2.URLError, urllib2.HTTPError) as e:
        print "Did not find a depends rosinstall file for %s" % repo

    return (doc_conf, depends_conf)

def install_repo(docspace, workspace, repo, doc_conf, depends_conf):
    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        print "Rosinstall for repo %s:\n%s"%(repo, doc_conf + depends_conf)
        yaml.safe_dump(doc_conf + depends_conf, f, default_flow_style=False)

    print "Created rosinstall file for repo %s, installing repo..."%repo
    #TODO Figure out why rosinstall insists on having ROS available when called with nobuild, but not catkin
    call("rosinstall %s %s --nobuild --catkin" % (docspace, os.path.join(workspace, "repo.rosinstall")))

#Find all the packages and stacks that have been installed
#Also build a map to go from each package or stack name to a repo name
def build_repo_structure(repo_path, doc_conf, depends_conf):
    stacks = {}
    manifest_packages = {}
    catkin_packages = {}
    repo_map = {}

    local_info = []
    for install_item in doc_conf + depends_conf:
        key = install_item.keys()[0]
        local_info.append({'type': key, 'name': install_item[key]['local-name'], 'url': install_item[key]['uri'], 'version': install_item[key].get('version', None)})

    #Get any stacks, manifest packages, or catkin packages (package.xml) in each repo
    for item in local_info:
        local_name = item['name']
        local_path = os.path.join(repo_path, local_name)
        print "Looking for the following packages in %s" % local_path
        local_stacks = get_repo_manifests(local_path, manifest='stack')
        local_manifest_packages = get_repo_manifests(local_path, manifest='package')
        local_catkin_packages = get_repo_packages(local_path)

        #Since rospkg is kind of screwed up and always finds package.xml files, we
        #need to filter out packages that are catkin_packages but still listed in
        #manifest or stack packages
        for name in local_catkin_packages.iterkeys():
            if name in local_stacks:
                del local_stacks[name]
            if name in local_manifest_packages:
                del local_manifest_packages[name]

        #Now, we need to update our repo map
        for name in local_stacks.keys() + local_manifest_packages.keys() + local_catkin_packages.keys():
            repo_map[name] = item

        #Finally, we'll merge these dictionaries into our global dicts
        stacks.update(local_stacks)
        manifest_packages.update(local_manifest_packages)
        catkin_packages.update(local_catkin_packages)

    return (stacks, manifest_packages, catkin_packages, repo_map)

