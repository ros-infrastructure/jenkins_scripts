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

import os
import re
import sys
import shutil
import subprocess
import copy
import rosdep

from common import call, call_with_list, append_pymodules_if_needed, \
    get_nonlocal_dependencies, build_local_dependency_graph, get_dependency_build_order, \
    copy_test_results, BuildException
from tags_db import TagsDb, build_tagfile
from doc_manifest import write_distro_specific_manifest, write_stack_manifests
from repo_structure import get_repositories_from_rosinstall, \
    load_configuration, install_repo, build_repo_structure, rev_changes
from message_generation import build_repo_messages_manifest, build_repo_messages, \
    build_repo_messages_catkin_stacks


def get_apt_deps(apt, ros_dep, ros_distro, catkin_packages, stacks, manifest_packages):
    apt_deps = []
    deps = get_nonlocal_dependencies(catkin_packages, stacks, manifest_packages)
    print("Dependencies: %s" % deps)
    for dep in deps:
        if ros_dep.has_ros(dep):
            apt_dep = ros_dep.to_apt(dep)
            if apt_dep and apt_dep[0]:
                apt_deps.extend(apt_dep)
        else:
            apt_dep = "ros-%s-%s" % (ros_distro, dep.replace('_', '-'))
            if apt.has_package(apt_dep):
                apt_deps.append(apt_dep)
            else:
                print("WARNING, could not find dependency %s, not adding to list" % dep)

    return apt_deps


def get_full_apt_deps(apt_deps, apt):
    full_apt_deps = copy.deepcopy(apt_deps)
    for dep in apt_deps:
        print("Getting dependencies for %s" % dep)
        full_apt_deps.extend(apt.depends(dep))

    #Make sure that we don't have any duplicates
    return list(set(full_apt_deps))


def document_packages(manifest_packages, catkin_packages, build_order,
                      repos_to_doc, sources, tags_db, full_apt_deps,
                      ros_dep, repo_map, repo_path, docspace, ros_distro,
                      homepage, doc_job, tags_location, doc_path,
                      rosdistro_release_file, rosdistro_source_file):
    repo_tags = {}
    for package in build_order:
        #don't document packages that we're supposed to build but not supposed to document
        if not repo_map[package]['name'] in repos_to_doc:
            print("Package: %s, in repo: %s, is not supposed to be documented. Skipping." % (package, repo_map[package]['name']))
            continue

        #Pull the package from the correct place
        if package in catkin_packages:
            package_path = catkin_packages[package]
        else:
            package_path = manifest_packages[package]

        print("Documenting %s [%s]..." % (package, package_path))

        pkg_status = None
        pkg_status_description = None
        pkg_release_jobs = []
        pkg_devel_jobs = []
        if package in catkin_packages:
            has_changelog_rst = document_package_changelog(package, package_path, doc_path)
            if rosdistro_release_file and package in rosdistro_release_file.packages:
                pkg_data = rosdistro_release_file.packages[package]
                repo_data = rosdistro_release_file.repositories[pkg_data.repository_name]
                if pkg_data.status is not None:
                    pkg_status = pkg_data.status
                elif repo_data.status is not None:
                    pkg_status = repo_data.status
                if pkg_data.status_description is not None:
                    pkg_status_description = pkg_data.status_description
                elif repo_data.status_description is not None:
                    pkg_status_description = repo_data.status_description
                if repo_data.version is not None:
                    pkg_release_jobs.append('ros-%s-%s_sourcedeb' % (ros_distro, package.replace('_', '-')))
                    for distro in rosdistro_release_file.platforms.get('ubuntu', []):
                        for arch in ['amd64', 'i386']:
                            pkg_release_jobs.append('ros-%s-%s_binarydeb_%s_%s' % (ros_distro, package.replace('_', '-'), distro, arch))

                if pkg_data.repository_name in rosdistro_source_file.repositories:
                    pkg_devel_jobs.append('devel-%s-%s' % (ros_distro, pkg_data.repository_name))
        else:
            has_changelog_rst = None

        #Build a tagfile list from dependencies for use by rosdoc
        build_tagfile(full_apt_deps, tags_db, 'rosdoc_tags.yaml', package, build_order, docspace, ros_distro, tags_location)

        relative_doc_path = "%s/doc/%s/api/%s" % (docspace, ros_distro, package)
        pkg_doc_path = os.path.realpath(relative_doc_path)
        relative_tags_path = "%s/tags/%s.tag" % (ros_distro, package)
        tags_path = os.path.realpath("%s/doc/%s" % (docspace, relative_tags_path))
        #Generate the command we'll use to document the stack
        command = ['bash', '-c', '%s \
                   && export ROS_PACKAGE_PATH=%s:$ROS_PACKAGE_PATH \
                   && rosdoc_lite %s -o %s -g %s -t rosdoc_tags.yaml'
                   % (' && '.join(sources), repo_path, package_path, pkg_doc_path, tags_path)]
        print('Invoking: %s' % ' '.join(command))
        rc = subprocess.call(command, stderr=subprocess.STDOUT)
        print('rosdoc_lite return code %d' % rc)

        add_canonical_link(pkg_doc_path, "%s/%s/api/%s" % (homepage, ros_distro, package))

        #Some doc runs won't generate tag files, so we need to check if they
        #exist before adding them to the list
        if(os.path.exists(tags_path)):
            package_tags = {'location': '%s' % (os.path.basename(relative_tags_path)),
                            'docs_url': '../../../api/%s/html' % (package),
                            'package': '%s' % package}

            # fetch generator specific output folders from rosdoc_lite
            from rosdoc_lite import get_generator_output_folders
            output_folders = get_generator_output_folders(package_path)
            print('output_folders', output_folders)
            for generator, output_folder in output_folders.items():
                package_tags['%s_output_folder' % generator] = output_folder

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
        #have available in this script like vcs location and type
        write_distro_specific_manifest(os.path.join(pkg_doc_path, 'manifest.yaml'),
                                       package, repo_map[package]['type'], repo_map[package]['url'], "%s/%s/api/%s/html" % (homepage, ros_distro, package),
                                       tags_db, repo_map[package]['name'], doc_job, repo_map[package]['version'], has_changelog_rst, pkg_status, pkg_status_description,
                                       pkg_release_jobs, pkg_devel_jobs)

        print("Done")
    return repo_tags


def add_canonical_link(base_path, base_link):
    print("add canonical link '%s' to all html files under '%s'...", base_link, base_path)
    for path, dirs, files in os.walk(base_path):
        for filename in [f for f in files if f.endswith('.html')]:
            f = os.path.join(path, filename)
            with open(f, 'r') as fh:
                data = fh.read()
            rel_path = os.path.relpath(f, base_path)
            link = os.path.join(base_link, rel_path)
            if data.find('rel="canonical"') != -1:
                continue
            data = data.replace('</head>', '<link rel="canonical" href="%s" />\n</head>' % link, 1)
            with open(f, 'w') as fh:
                fh.write(data)


def document_package_changelog(pkg_name, pkg_path, doc_path):
    from docutils.core import publish_string
    assert os.path.exists(os.path.join(pkg_path, 'package.xml'))
    changelog_file = os.path.join(pkg_path, 'CHANGELOG.rst')
    if os.path.exists(changelog_file):
        print('Package "%s" contains a CHANGELOG.rst, generate html' % pkg_name)
        with open(changelog_file, 'r') as f:
            rst_code = f.read()
        html_code = publish_string(rst_code, writer_name='html')

        # strip system message from html output
        open_tag = re.escape('<div class="first system-message">')
        close_tag = re.escape('</div>')
        pattern = '(' + open_tag + '.+?' + close_tag + ')'
        html_code = re.sub(pattern, '', html_code, flags=re.DOTALL)

        pkg_changelog_doc_path = os.path.join(doc_path, 'changelogs', pkg_name)
        os.makedirs(pkg_changelog_doc_path)
        with open(os.path.join(pkg_changelog_doc_path, 'changelog.html'), 'w') as f:
            f.write(html_code)
        return True
    return False


def extract_notification_recipients(docspace, doc_conf):
    repo_path = os.path.realpath("%s" % (docspace))
    _, manifest_packages, catkin_packages, _ = build_repo_structure(repo_path, doc_conf, [])
    notification_recipients = set([])
    email_pattern = re.compile('([a-zA-Z0-9._%\+-]+@[a-zA-Z0-9._%-]+\.[a-zA-Z]{2,6})')
    for package_name in set(catkin_packages.keys()) | set(manifest_packages.keys()):
        if package_name in catkin_packages:
            package_path = catkin_packages[package_name]
            from catkin_pkg.package import parse_package
            pkg = parse_package(package_path)
            for m in pkg.maintainers:
                notification_recipients.add(m.email)
        else:
            package_path = manifest_packages[package_name]
            from rospkg import MANIFEST_FILE, STACK_FILE
            from rospkg.manifest import parse_manifest_file
            if os.path.exists(os.path.join(package_path, MANIFEST_FILE)):
                pkg = parse_manifest_file(package_path, MANIFEST_FILE)
            elif os.path.exists(os.path.join(package_path, STACK_FILE)):
                pkg = parse_manifest_file(package_path, STACK_FILE)
            else:
                assert False, "Path '%s' does not neither contain a manifest.xml nor a stack.xml file" % package_path
            if pkg.author:
                for email in email_pattern.finditer(pkg.author):
                    notification_recipients.add(email.group(1))
    if notification_recipients:
        print('Notification recipients: %s' % ' '.join(sorted(notification_recipients)))


def document_necessary(workspace, docspace, ros_distro, repo,
                       rosdoc_lite_version, jenkins_scripts_version, force_doc=False):
    append_pymodules_if_needed()
    print("Working on distro %s and repo %s" % (ros_distro, repo))

    #Load the rosinstall configurations for the repository
    doc_conf, depends_conf = load_configuration(ros_distro, repo)

    #Install the repository
    try:
        install_repo(docspace, workspace, repo, doc_conf, depends_conf)
    except BuildException:
        # checkout failed, try to get default branches of repos to notify the maintainers
        print('Failed to checkout repositories, trying to checkout default branches to collect maintainer information for notification about failure')
        for tuple in doc_conf:
            for repo in tuple.values():
                repo['version'] = None
        install_repo(docspace, workspace, repo, doc_conf, [])
        extract_notification_recipients(docspace, doc_conf)
        raise

    extract_notification_recipients(docspace, doc_conf)

    #Load information about existing tags
    jenkins_scripts_path = os.path.join(workspace, 'jenkins_scripts')
    if not os.path.exists(jenkins_scripts_path):
        # if jenkins_scripts has not been checked out in the workspace
        # expect that the user call doc from within a jenkins_scripts checkout
        jenkins_scripts_path = os.getcwd()
    rosdoc_tag_index_path = os.path.join(workspace, 'rosdoc_tag_index')
    tags_db = TagsDb(ros_distro, jenkins_scripts_path, rosdoc_tag_index_path)

    #Check to see if we need to document this repo list by checking if any of
    #the repositories revision numbers/hashes have changed
    changes = False or force_doc
    for conf in [('%s' % repo, doc_conf), ('%s_depends' % repo, depends_conf)]:
        changes = rev_changes(conf[0], conf[1], docspace, tags_db) or changes

    #We also want to make sure that we run documentation generation anytime
    #jenkins_scripts or rosdoc_lite has changed since the last time this job was
    #run
    repo_hashes = tags_db.get_rosinstall_hashes(repo) if tags_db.has_rosinstall_hashes(repo) else {}
    old_rosdoc_lite_hash = repo_hashes.get('rosdoc_lite-sys', None)
    old_jenkins_scripts_hash = repo_hashes.get('jenkins_scripts-sys', None)
    print("REPO HASHES: %s" % repo_hashes)

    if not changes and old_rosdoc_lite_hash == rosdoc_lite_version and old_jenkins_scripts_hash == jenkins_scripts_version:
        print("There were no changes to any of the repositories we document. Not running documentation.")
        copy_test_results(workspace, docspace)
        tags_db.delete_tag_index_repo()

        # create marker files for all packages an upload them
        doc_path = os.path.realpath("%s/doc/%s" % (docspace, ros_distro))
        if os.path.exists(doc_path):
            shutil.rmtree(doc_path)
        repo_path = os.path.realpath("%s" % (docspace))
        stacks, manifest_packages, catkin_packages, _ = build_repo_structure(repo_path, doc_conf, depends_conf)
        folders = sorted(set(stacks.keys() + manifest_packages.keys() + catkin_packages.keys()))
        if folders:
            dsts = ['%s/api/%s/stamp' % (doc_path, f) for f in folders]
            for dst in dsts:
                os.makedirs(os.path.dirname(dst))
                with open(dst, 'w'):
                    pass
            print("Uploading marker files to identify that documentation is up-to-date.")
            command = ['bash', '-c', 'rsync -e "ssh -o StrictHostKeyChecking=no" -qr %s/api/ rosbot@ros.osuosl.org:/home/rosbot/docs/%s/api' % (doc_path, ros_distro)]
            call_with_list(command)

        return False

    #Make sure to update the versions of jenkins_scripts and rosdoc_lite for this repo list
    repo_hashes['rosdoc_lite-sys'] = rosdoc_lite_version
    repo_hashes['jenkins_scripts-sys'] = jenkins_scripts_version
    tags_db.set_rosinstall_hashes(repo, repo_hashes)
    return {'doc_conf': doc_conf, 'depends_conf': depends_conf, 'tags_db': tags_db}


def document_repo(workspace, docspace, ros_distro, repo,
                  platform, arch, homepage, no_chroot, skip_garbage,
                  doc_conf, depends_conf, tags_db):
    doc_job = "doc-%s-%s" % (ros_distro, repo)

    #Get the list of repositories that should have documentation run on them
    #These are all of the repos that are not in the depends rosinsall file
    repos_to_doc = get_repositories_from_rosinstall(doc_conf)

    repo_path = os.path.realpath("%s" % (docspace))
    print("Repo path %s" % repo_path)

    #Walk through the installed repositories and find old-style packages, new-stye packages, and stacks
    stacks, manifest_packages, catkin_packages, repo_map = build_repo_structure(repo_path, doc_conf, depends_conf)
    if ros_distro == 'indigo':
        if stacks or manifest_packages:
            print("Ignoring dry packages and stacks in '%s'" % ros_distro)
            stacks = {}
            manifest_packages = {}
        if not catkin_packages:
            raise BuildException('No catkin packages found')
    print("Running documentation generation on\npackages: %s" % (manifest_packages.keys() + catkin_packages.keys()))
    #print "Catkin packages: %s" % catkin_packages
    #print "Manifest packages: %s" % manifest_packages
    #print "Stacks: %s" % stacks

    #Get any non local apt dependencies
    ros_dep = rosdep.RosDepResolver(ros_distro, no_chroot=no_chroot)
    import rosdistro
    if ros_distro == 'electric':
        apt = rosdistro.AptDistro(platform, arch, shadow=False)
    else:
        apt = rosdistro.AptDistro(platform, arch, shadow=True)
    apt_deps = get_apt_deps(apt, ros_dep, ros_distro, catkin_packages, stacks, manifest_packages)
    print("Apt dependencies: %s" % apt_deps)

    #Get rosdistro release file if there are catkin packages to get status
    if catkin_packages and ros_distro not in ['electric', 'fuerte']:
        print("Fetch rosdistro files for: %s" % ros_distro)
        index = rosdistro.get_index(rosdistro.get_index_url())
        rosdistro_release_file = rosdistro.get_release_file(index, ros_distro)
        rosdistro_source_file = rosdistro.get_source_file(index, ros_distro)
    else:
        rosdistro_release_file = None
        rosdistro_source_file = None

    #Build a local dependency graph to be used for build order
    local_dep_graph = build_local_dependency_graph(catkin_packages, manifest_packages)

    doc_path = os.path.realpath("%s/doc/%s" % (docspace, ros_distro))
    if os.path.exists(doc_path):
        shutil.rmtree(doc_path)

    #Write stack manifest files for all stacks, we can just do this off the
    #stack.xml files
    write_stack_manifests(stacks, docspace, ros_distro, repo_map, tags_db, doc_job, homepage)

    #Need to make sure to re-order packages to be run in dependency order
    build_order = get_dependency_build_order(local_dep_graph)
    print("Build order that honors deps:\n%s" % build_order)

    #We'll need the full list of apt_deps to get tag files
    full_apt_deps = get_full_apt_deps(apt_deps, apt)

    if not no_chroot:
        print("Installing all dependencies for %s" % repo)

        # XXX this is a really ugly hack to make the hydro doc job for ros_comm pass
        # otherwise roslisp pulls in the rosgraph_msgs package as a Debian dependency
        # which then break catkin_basic since it include the msgs CMake multiple files
        # resulting in duplicate target names (https://github.com/ros/ros_comm/issues/471)
        if repo == 'ros_comm' and 'ros-hydro-roslisp' in apt_deps:
            apt_deps.remove('ros-hydro-roslisp')

        if apt_deps:
            call("apt-get install %s --yes" % (' '.join(apt_deps)))
        print("Done installing dependencies")

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
    local_install_path = os.path.join(docspace, 'local_installs')
    if os.path.exists(local_install_path):
        shutil.rmtree(local_install_path)

    #Make sure to create some subfolders under the local install path
    def makedirs(path):
        if not os.path.exists(path):
            os.makedirs(path)

    makedirs(os.path.join(local_install_path, 'bin'))
    makedirs(os.path.join(local_install_path, 'lib/python2.7/dist-packages'))
    makedirs(os.path.join(local_install_path, 'share'))

    if catkin_packages \
       and not 'rosdoc_lite' in catkin_packages.keys() and not 'catkin' in catkin_packages.keys():
        source, errs = build_repo_messages(catkin_packages, docspace, ros_distro, local_install_path)
        build_errors.extend(errs)
        if source:
            sources.append(source)

    #For fuerte catkin, we need to check if we should build catkin stacks
    source, errs = build_repo_messages_catkin_stacks(stacks, ros_distro, local_install_path)
    build_errors.extend(errs)
    sources.append(source)

    #For all our manifest packages (dry or fuerte catkin) we want to build
    #messages. Note, for fuerte catkin, we have to build all the code and
    #install locally to get message generation
    source, errs = build_repo_messages_manifest(manifest_packages, build_order, ros_distro)
    build_errors.extend(errs)
    sources.append(source)

    #We want to pull all the tagfiles available once from the server
    tags_location = os.path.join(workspace, ros_distro)
    if os.path.exists(tags_location):
        shutil.rmtree(tags_location)
    command = ['bash', '-c',
               'rsync -e "ssh -o StrictHostKeyChecking=no" -qrz rosbot@ros.osuosl.org:/home/rosbot/docs/%s/tags %s' % (ros_distro, tags_location)]
    call_with_list(command)

    repo_tags = document_packages(manifest_packages, catkin_packages, build_order,
                                  repos_to_doc, sources, tags_db, full_apt_deps,
                                  ros_dep, repo_map, repo_path, docspace, ros_distro,
                                  homepage, doc_job, tags_location, doc_path,
                                  rosdistro_release_file, rosdistro_source_file)

    #Copy the files to the appropriate place
    folders = sorted(set(stacks.keys() + manifest_packages.keys() + catkin_packages.keys()))
    if folders:
        dsts = ['%s/api/%s' % (doc_path, f) for f in folders]
        for dst in dsts:
            with open(os.path.join(dst, 'stamp'), 'w'):
                pass
        command = ['bash', '-c', 'rsync -e "ssh -o StrictHostKeyChecking=no" -qr --delete %s rosbot@ros.osuosl.org:/home/rosbot/docs/%s/api' % (' '.join(dsts), ros_distro)]
        call_with_list(command)
    folders = ['%s/changelogs' % doc_path, '%s/tags' % doc_path]
    folders = [f for f in folders if os.path.exists(f)]
    if folders:
        command = ['bash', '-c', 'rsync -e "ssh -o StrictHostKeyChecking=no" -qr %s rosbot@ros.osuosl.org:/home/rosbot/docs/%s' % (' '.join(folders), ros_distro)]
        call_with_list(command)

    if not skip_garbage:
        #Remove the autogenerated doc files since they take up a lot of space if left on the server
        shutil.rmtree(tags_location)
        shutil.rmtree(doc_path)

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
    #We don't want to write hashes on an unsuccessful build
    excludes = ['rosinstall_hashes'] if build_errors else []
    tags_db.commit_db(excludes)
    tags_db.delete_tag_index_repo()

    #Tell jenkins that we've succeeded
    print("Preparing xml test results")
    try:
        os.makedirs(os.path.join(workspace, 'test_results'))
        print("Created test results directory")
    except Exception:
        pass

    if build_errors:
        import yaml
        copy_test_results(workspace, docspace,
                          """Failed to generate messages by calling cmake for %s.
Look in the console for cmake failures, search for "CMake Error"

Also, are you sure that the rosinstall files are pulling from the right branch for %s? Check the repos below,
you can update information the %s.rosinstall and %s-depends.rosinstall files by submitting a pull request at
https://github.com/ros/rosdistro/%s

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
