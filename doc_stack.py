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
# Revision $Id: rosdoc 11469 2010-10-12 00:56:25Z kwc $

import urllib2
import os
import sys
import yaml
import subprocess
import copy
import time
from common import call, call_with_list, append_pymodules_if_needed, AptDepends, RosDepResolver, \
                   get_nonlocal_dependencies, build_local_dependency_graph, get_dependency_build_order, \
                   copy_test_results
from tags_db import TagsDb, build_tagfile
from doc_manifest import write_stack_manifest, write_distro_specific_manifest, write_stack_manifests
from repo_structure import get_repo_manifests, get_repo_packages, get_repositories_from_rosinstall, \
                           load_configuration, install_repo, build_repo_structure
from message_generation import generate_messages_catkin, generate_messages_dry, \
                               build_repo_messages_manifest, build_repo_messages

def get_apt_deps(apt, ros_dep, ros_distro, catkin_packages, stacks, manifest_packages):
    apt_deps = []
    deps = get_nonlocal_dependencies(catkin_packages, stacks, manifest_packages)
    print "Dependencies: %s" % deps
    for dep in deps:
        if ros_dep.has_ros(dep):
            apt_dep = ros_dep.to_apt(dep)
            apt_deps.extend(apt_dep)
        else:
            apt_dep = "ros-%s-%s" % (ros_distro, dep.replace('_', '-'))
            if apt.has_package(apt_dep):
                apt_deps.append(apt_dep)
            else:
                print "WARNING, could not find dependency %s, not adding to list" % dep

    return apt_deps

def get_full_apt_deps(apt_deps, apt):
    full_apt_deps = copy.deepcopy(apt_deps)
    for dep in apt_deps:
        print "Getting dependencies for %s" % dep
        full_apt_deps.extend(apt.depends(dep))

    #Make sure that we don't have any duplicates
    return list(set(full_apt_deps))

def document_packages(manifest_packages, catkin_packages, build_order, 
                      repos_to_doc, sources, tags_db, full_apt_deps,
                      ros_dep, repo_map, repo_path, docspace, ros_distro, 
                      homepage, doc_job):
    repo_tags = {}
    for package in build_order:
        #don't document packages that we're supposed to build but not supposed to document
        if not repo_map[package]['name'] in repos_to_doc:
            print "Package: %s, in repo: %s, is not supposed to be documented. Skipping." % (package, repo_map[package]['name'])
            continue

        #Pull the package from the correct place
        if package in catkin_packages:
            package_path = catkin_packages[package]
        else:
            package_path = manifest_packages[package]

        #Build a tagfile list from dependencies for use by rosdoc
        build_tagfile(full_apt_deps, tags_db, 'rosdoc_tags.yaml', package, build_order, docspace, ros_distro)

        relative_doc_path = "%s/doc/%s/api/%s" % (docspace, ros_distro, package)
        pkg_doc_path = os.path.abspath(relative_doc_path)
        relative_tags_path = "%s/api/%s/tags/%s.tag" % (ros_distro, package, package)
        tags_path = os.path.abspath("%s/doc/%s" % (docspace, relative_tags_path))
        print "Documenting %s [%s]..." % (package, package_path)
        #Generate the command we'll use to document the stack
        command = ['bash', '-c', '%s \
                   && export ROS_PACKAGE_PATH=%s:$ROS_PACKAGE_PATH \
                   && rosdoc_lite %s -o %s -g %s -t rosdoc_tags.yaml' \
                   %(' && '.join(sources), repo_path, package_path, pkg_doc_path, tags_path) ]
        #proc = subprocess.Popen(command, stdout=subprocess.PIPE)
        proc = subprocess.Popen(command)
        proc.communicate()

        #Some doc runs won't generate tag files, so we need to check if they
        #exist before adding them to the list
        if(os.path.exists(tags_path)):
            package_tags = {'location':'%s/%s'%(homepage, relative_tags_path), 
                                 'docs_url':'../../../api/%s/html'%(package), 
                                 'package':'%s'%package}

            #If the package has a deb name, then we'll store the tags for it
            #alongside that name
            if ros_dep.has_ros(package):
                pkg_deb_name = ros_dep.to_apt(package)[0]
                tags_db.set_tags(pkg_deb_name, [package_tags])
            #Otherwise, we'll store tags for it alongside it's repo, which we
            #assume can be made into a deb name
            else:
                repo_tags.setdefault(repo_map[package]['name'], []).append(package_tags)

        #We also need to add information to each package manifest that we only
        #have availalbe in this script like vcs location and type
        write_distro_specific_manifest(os.path.join(pkg_doc_path, 'manifest.yaml'),
                                       package, repo_map[package]['type'], repo_map[package]['url'], "%s/%s/api/%s/html" %(homepage, ros_distro, package),
                                       tags_db, repo_map[package]['name'], doc_job, repo_map[package]['version'])

        print "Done"
    return repo_tags


def document_repo(workspace, docspace, ros_distro, repo, platform, arch, homepage):
    append_pymodules_if_needed()
    doc_job = "doc-%s-%s" % (ros_distro, repo)
    print "Working on distro %s and repo %s" % (ros_distro, repo)

    #Load the rosinstall configurations for the repository
    doc_conf, depends_conf = load_configuration(ros_distro, repo)

    #Get the list of repositories that should have documentation run on them
    #These are all of the repos that are not in the depends rosinsall file
    repos_to_doc = get_repositories_from_rosinstall(doc_conf)

    #Install the repository
    install_repo(docspace, workspace, repo, doc_conf, depends_conf)
    repo_path = os.path.abspath("%s" % (docspace))
    print "Repo path %s" % repo_path

    #Walk through the installed repositories and find old-style packages, new-stye packages, and stacks
    stacks, manifest_packages, catkin_packages, repo_map = build_repo_structure(repo_path, doc_conf, depends_conf)
    print "Running documentation generation on\npackages: %s" % (manifest_packages.keys() + catkin_packages.keys())
    print "Catkin packages: %s" % catkin_packages
    print "Manifest packages: %s" % manifest_packages
    print "Stacks: %s" % stacks

    #Load information about existing tags
    tags_db = TagsDb(ros_distro, workspace)

    #Get any non local apt dependencies
    ros_dep = RosDepResolver(ros_distro)
    if ros_distro == 'electric':
        apt = AptDepends(platform, arch, shadow=False)
    else:
        apt = AptDepends(platform, arch, shadow=True)
    apt_deps = get_apt_deps(apt, ros_dep, ros_distro, catkin_packages, stacks, manifest_packages)
    print "Apt dependencies: %s" % apt_deps

    #Build a local dependency graph to be used for build order
    local_dep_graph = build_local_dependency_graph(catkin_packages, manifest_packages)

    #Write stack manifest files for all stacks, we can just do this off the
    #stack.xml files
    write_stack_manifests(stacks, docspace, ros_distro, repo_map, tags_db, doc_job, homepage)

    #Need to make sure to re-order packages to be run in dependency order
    build_order = get_dependency_build_order(local_dep_graph)
    print "Build order that honors deps:\n%s" % build_order

    #We'll need the full list of apt_deps to get tag files
    full_apt_deps = get_full_apt_deps(apt_deps, apt)

    print "Installing all dependencies for %s" % repo
    if apt_deps:
        call("apt-get install %s --yes" % (' '.join(apt_deps)))
    print "Done installing dependencies"

    #Set up the list of things that need to be sourced to run rosdoc_lite
    #TODO: Hack for electric
    if ros_distro == 'electric':
        #lucid doesn't have /usr/local on the path by default... weird
        sources = ['export PATH=/usr/local/sbin:/usr/local/bin:$PATH']
        sources.append('source /opt/ros/fuerte/setup.bash')
        sources.append('export ROS_PACKAGE_PATH=/opt/ros/electric/stacks:$ROS_PACKAGE_PATH')
    else:
        sources = ['source /opt/ros/%s/setup.bash' % ros_distro]

    #We assume that there will be no build errors to start
    build_errors = []

    #Everything that is after fuerte supports catkin workspaces, so everything
    #that has packages with package.xml files
    if catkin_packages \
       and not 'rosdoc_lite' in catkin_packages.keys() and not 'catkin' in catkin_packages.keys():
        source, errs = build_repo_messages(catkin_packages, docspace, ros_distro)
        build_errors.extend(errs)
        if source:
            sources.append(source)

    #For all our manifest packages (dry or fuerte catkin) we want to build
    #messages. Note, for fuerte catkin the messages arent' generated, TODO
    #to come back and fix this if necessary
    source, errs = build_repo_messages_manifest(manifest_packages, build_order, ros_distro)
    build_errors.extend(errs)
    sources.append(source)

    repo_tags = document_packages(manifest_packages, catkin_packages, build_order, 
                                  repos_to_doc, sources, tags_db, full_apt_deps,
                                  ros_dep, repo_map, repo_path, docspace, ros_distro,
                                  homepage, doc_job)

    doc_path = os.path.abspath("%s/doc/%s" % (docspace, ros_distro))

    #Copy the files to the appropriate place
    #call("rsync -e \"ssh -o StrictHostKeyChecking=no\" -qr %s rosbuild@wgs32:/var/www/www.ros.org/html/rosdoclite" % (doc_path))
    command = ['bash', '-c', 'rsync -e "ssh -o StrictHostKeyChecking=no" -qr %s rosbuild@wgs32:/var/www/www.ros.org/html/rosdoclite' % doc_path]
    call_with_list(command)

    #Write the new tags to the database if there are any to write
    for name, tags in repo_tags.iteritems():
        #Get the apt name of the current stack/repo
        if ros_dep.has_ros(name):
            deb_name = ros_dep.to_apt(name)[0]
        else:
            deb_name = "ros-%s-%s" % (ros_distro, name.replace('_', '-'))

        #We only want to write tags for packages that have a valid deb name
        #For others, the only way to get cross referencing is to document everything
        #together with a rosinstall file
        if apt.has_package(deb_name):
            tags_db.set_tags(deb_name, tags)

    #Make sure to write changes to tag files and deps
    tags_db.commit_db()

    #Tell jenkins that we've succeeded
    print "Preparing xml test results"
    try:
        os.makedirs(os.path.join(workspace, 'test_results'))
        print "Created test results directory"
    except:
        pass

    if build_errors:
        copy_test_results(workspace, docspace, 
                          """Failed to generate messages by calling cmake for %s. 
Look in the console for cmake failures, search for "CMake Error"

Also, are you sure that the rosinstall files are pulling from the right branch for %s? Check the repos below,
you can update information the %s.rosinstall and %s-depends.rosinstall files by submitting a pull request at
https://github.com/ros/rosdistro/tree/master/doc/%s

Documentation rosinstall:\n%s

Depends rosinstall:\n%s""" % (build_errors, 
                              ros_distro,
                              repo,
                              repo,
                              ros_distro,
                              yaml.safe_dump(doc_conf, default_flow_style=False), 
                              yaml.safe_dump(depends_conf, default_flow_style=False)),
                          "message_generation_failure")
    else:
        copy_test_results(workspace, docspace)

def main():
    arguments = sys.argv[1:]
    ros_distro = arguments[0]
    stack = arguments[1]
    workspace = 'workspace'
    docspace = 'docspace'
    homepage = 'http://ros.org/doc'

    document_repo(workspace, docspace, ros_distro, stack, 'precise', 'amd64', homepage)

if __name__ == '__main__':
    main()
