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
import fnmatch
import copy
import time
from common import *
from tags_db import *

def write_stack_manifest(output_dir, stack_name, manifest, 
                         vcs_type, vcs_uri, api_homepage, 
                         packages, tags_db, repo_name, doc_job):
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
                                   repo_name, doc_job):
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

def build_tagfile(apt_deps, tags_db, rosdoc_tagfile, current_package, ordered_deps, docspace, ros_distro):
    #Get the relevant tags from the database
    tags = []

    for dep in apt_deps:
        if tags_db.has_tags(dep):
            #Make sure that we don't pass our own tagfile to ourself
            #bad things happen when we do this
            for tag in tags_db.get_tags(dep):
                if tag['package'] != current_package:
                    tags.append(tag)

    #Add tags built locally in dependency order
    for dep in ordered_deps:
        #we'll exit the loop when we reach ourself
        if dep == current_package:
            break

        relative_tags_path = "doc/%s/api/%s/tags/%s.tag" % (ros_distro, dep, dep)
        if os.path.isfile(os.path.join(docspace, relative_tags_path)):
            tags.append({'docs_url': '../../%s/html' % dep, 
                         'location': 'file://%s' % os.path.join(docspace, relative_tags_path),
                         'package': '%s' % dep})
        else:
            print "DID NOT FIND TAG FILE at: %s" % os.path.join(docspace, relative_tags_path)

    with open(rosdoc_tagfile, 'w+') as tags_file:
        yaml.dump(tags, tags_file)

def generate_messages_catkin(env):
    try:
        targets = call("make help", env).split('\n')
    except BuildException as e:
        return

    genpy_targets = [t.split()[1] for t in targets if t.endswith("genpy")]
    print genpy_targets
    for t in genpy_targets:
        call("make %s" % t, env)

def generate_messages_dry(env, name):
    try:
        targets = call("make help", env).split('\n')
    except BuildException as e:
        return

    if [t for t in targets if t.endswith("ROSBUILD_genaction_msgs")]:
        call("make ROSBUILD_genaction_msgs", env)

    if [t for t in targets if t.endswith("ROSBUILD_genmsg_py")]:
        call("make ROSBUILD_genmsg_py", env)
        print "Generated messages for %s" % name
        
def build_repo_messages_manifest(manifest_packages, build_order, ros_distro):
    #Now, we go through all of our manifest packages and try to generate
    #messages, or add them to the pythonpath if they turn out to be catkin
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' %ros_distro)
    path_string = ''
    build_errors = []

    #Make sure to build in dependency order
    for name in build_order:
        if not name in manifest_packages or name == 'rosdoc_lite':
            continue

        path = manifest_packages[name]

        cmake_file = os.path.join(path, 'CMakeLists.txt')
        if os.path.isfile(cmake_file):
            catkin = False
            #Check to see whether the package is catkin or not
            with open(cmake_file, 'r') as f:
                if 'catkin_project' in f.read():
                    catkin = True

            #If it is catkin, then we'll do our best to put the right things on the python path
            #TODO: Note that this will not generate messages, we can try to put this in later
            #but fuerte catkin makes it kind of hard to do correctly
            if catkin:
                print "Creating an export line that guesses the appropriate python paths for each package"
                print "WARNING: This will not properly generate message files within this repo for python documentation."
                if os.path.isdir(os.path.join(path, 'src')):
                    path_string = "%s:%s" %(os.path.join(path, 'src'), path_string)

            #If it's not catkin, then we'll generate python messages
            else:
                old_dir = os.getcwd()
                os.chdir(path)
                if not os.path.exists('build'):
                    os.makedirs('build')
                os.chdir('build')
                ros_env['ROS_PACKAGE_PATH'] = '%s:%s' % (path, ros_env['ROS_PACKAGE_PATH'])
                print "Calling cmake .. on %s, with env path %s" % (name, ros_env)
                try:
                    call("cmake ..", ros_env)
                    generate_messages_dry(ros_env, name)
                except BuildException as e:
                    print "FAILED TO CALL CMAKE ON %s, messages for this package cannot be generated." % (name)
                    print "Are you sure that the package specifies its dependencies correctly?"
                    print "Exception: %s" % e
                    build_errors.append(name)
                os.chdir(old_dir)
        else:
            #If the package does not have a CmakeLists.txt file, we still want
            #to add it to our package path because other packages may depend on it
            ros_env['ROS_PACKAGE_PATH'] = '%s:%s' % (path, ros_env['ROS_PACKAGE_PATH'])

    if path_string:
        return ("export PYTHONPATH=%s:$PYTHONPATH" % path_string, build_errors)

    return ("export PYTHONPATH=$PYTHONPATH", build_errors)

def build_repo_messages(docspace, ros_distro):
    build_errors = []
    #For groovy, this isn't too bad, we just set up a workspace
    old_dir = os.getcwd()
    repo_buildspace = os.path.join(docspace, 'build_repo')
    if not os.path.exists(repo_buildspace):
        os.makedirs(repo_buildspace)
    os.chdir(repo_buildspace)
    print "Removing the CMakeLists.txt file generated by rosinstall"
    os.remove(os.path.join(docspace, 'CMakeLists.txt'))
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' %ros_distro)
    print "Calling cmake..."
    call("catkin_init_workspace %s"%docspace, ros_env)
    try:
        call("cmake ..", ros_env)
        ros_env = get_ros_env(os.path.join(repo_buildspace, 'buildspace/setup.bash'))
        generate_messages_catkin(ros_env)
        source = 'source %s' % (os.path.abspath(os.path.join(repo_buildspace, 'buildspace/setup.bash')))
    except BuildException as e:
        print "FAILED TO CALL CMAKE ON CATKIN REPOS"
        print "There will be no messages in documentation and some python docs may fail"
        print "Exception: %s" % e
        source = ''
        build_errors.append("catkin_workspace for repository")
    os.chdir(old_dir)
    return (source, build_errors)

def get_repositories_from_rosinstall(rosinstall):
    repos = []
    for item in rosinstall:
        key = item.keys()[0]
        repos.append(item[key]['local-name'])
    return repos

def document_repo(workspace, docspace, ros_distro, repo, platform, arch):
    doc_job = "doc-%s-%s-%s-%s" % (ros_distro, repo, platform, arch)
    append_pymodules_if_needed()
    print "Working on distro %s and repo %s" % (ros_distro, repo)
    try:
        repo_url = 'https://raw.github.com/ros/rosdistro/master/doc/%s/%s.rosinstall'%(ros_distro, repo)
        f = urllib2.urlopen(repo_url)
        if f.code != 200:
            raise BuildException("Could not find a valid rosinstall file for %s at %s" % (repo, repo_url))
        conf = yaml.load(f.read())
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

    #Get the list of repositories that should have documentation run on them
    #These are all of the repos that are not in the depends rosinsall file
    repos_to_doc = get_repositories_from_rosinstall(conf)

    #TODO: Change this or parameterize or whatever
    homepage = 'http://ros.org/rosdoclite'

    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        print "Rosinstall for repo %s:\n%s"%(repo, conf + depends_conf)
        yaml.safe_dump(conf + depends_conf, f, default_style=False)

    print "Created rosinstall file for repo %s, installing repo..."%repo
    #TODO Figure out why rosinstall insists on having ROS available when called with nobuild, but not catkin
    call("rosinstall %s %s --nobuild --catkin" % (docspace, os.path.join(workspace, "repo.rosinstall")))

    repo_path = os.path.abspath("%s" % (docspace))
    print "Repo path %s" % repo_path

    stacks = {}
    manifest_packages = {}
    catkin_packages = {}
    repo_map = {}

    local_info = []
    for install_item in conf + depends_conf:
        key = install_item.keys()[0]
        local_info.append({'type': key, 'name': install_item[key]['local-name'], 'url': install_item[key]['uri']})

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

    print "Running documentation generation on\npackages: %s" % (manifest_packages.keys() + catkin_packages.keys())

    print "Catkin packages: %s" % catkin_packages
    print "Manifest packages: %s" % manifest_packages
    print "Stacks: %s" % stacks

    #Load information about existing tags
    tags_db = TagsDb(ros_distro, workspace)

    #Get any non local dependencies and install them
    apt_deps = []
    ros_dep = RosDepResolver(ros_distro)
    apt = AptDepends(platform, arch)
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


    print "Apt dependencies: %s" % apt_deps

    #Build a local dependency graph to be used for build order
    local_dep_graph = build_local_dependency_graph(catkin_packages, manifest_packages)

    #Write stack manifest files for all stacks, we can just do this off the
    #stack.xml files
    for stack, path in stacks.iteritems():
        import rospkg
        #Get the dependencies of a dry stack from the stack.xml
        stack_manifest = rospkg.parse_manifest_file(path, rospkg.STACK_FILE)
        stack_packages = get_repo_manifests(path, manifest='package').keys()
        deps = [d.name for d in stack_manifest.depends]
        stack_relative_doc_path = "%s/doc/%s/api/%s" % (docspace, ros_distro, stack)
        stack_doc_path = os.path.abspath(stack_relative_doc_path)
        write_stack_manifest(stack_doc_path, stack, stack_manifest, repo_map[stack]['type'], repo_map[stack]['url'], "%s/%s/api/%s/html" %(homepage, ros_distro, stack), stack_packages, tags_db, repo_map[stack]['name'], doc_job)

    #Need to make sure to re-order packages to be run in dependency order
    build_order = get_dependency_build_order(local_dep_graph)
    print "Build order that honors deps:\n%s" % build_order

    #We'll need the full list of apt_deps to get tag files
    full_apt_deps = copy.deepcopy(apt_deps)
    for dep in apt_deps:
        print "Getting dependencies for %s" % dep
        full_apt_deps.extend(apt.depends(dep))

    #Make sure that we don't have any duplicates
    full_apt_deps = list(set(full_apt_deps))

    print "Installing all dependencies for %s" % repo
    if apt_deps:
        call("apt-get install %s --yes" % (' '.join(apt_deps)))
    print "Done installing dependencies"

    #Set up the list of things that need to be sourced to run rosdoc_lite
    sources = ['source /opt/ros/%s/setup.bash' % ros_distro]

    #We assume that there will be no build errors to start
    build_errors = []

    #Everything that is after fuerte supports catkin workspaces, so everything
    #that has packages with package.xml files
    if catkin_packages and not 'rosdoc_lite' in catkin_packages.keys():
        source, errs = build_repo_messages(docspace, ros_distro)
        build_errors.extend(errs)
        if source:
            sources.append(source)

    #For all our manifest packages (dry or fuerte catkin) we want to build
    #messages. Note, for fuerte catkin the messages arent' generated, TODO
    #to come back and fix this if necessary
    source, errs = build_repo_messages_manifest(manifest_packages, build_order, ros_distro)
    build_errors.extend(errs)
    sources.append(source)

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
                                       tags_db, repo_map[package]['name'], doc_job)

        print "Done"

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
        copy_test_results(workspace, docspace, "Failed to generate messages by calling cmake for %s. Look in console for cmake failures." % build_errors)
    else:
        copy_test_results(workspace, docspace)

def main():
    arguments = sys.argv[1:]
    ros_distro = arguments[0]
    stack = arguments[1]
    workspace = 'workspace'
    docspace = 'docspace'
    document_repo(workspace, docspace, ros_distro, stack, 'precise', 'amd64')

if __name__ == '__main__':
    main()
