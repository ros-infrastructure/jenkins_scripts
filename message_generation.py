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
import shutil
from common import call, check_output, get_ros_env, BuildException

catkin_cmake_file = """cmake_minimum_required(VERSION 2.8.3)
find_package(catkin_basic REQUIRED)
catkin_basic()"""

manifest_cmake_file = """cmake_minimum_required(VERSION 2.4.6)
include($ENV{ROS_ROOT}/core/rosbuild/rosbuild.cmake)"""

actionlib_msgs_include = """
rosbuild_find_ros_package(actionlib_msgs)
include(${actionlib_msgs_PACKAGE_PATH}/cmake/actionbuild.cmake)
"""

manifest_build_targets = """
{genaction}
rosbuild_init()
{genmsg}
{gensrv}"""


#We want to remove all export lines from package.xml and manifest.xml files
#that are not rosdoc or metpackage related
def remove_export_tags(path):
    import xml.etree.ElementTree as ElementTree
    et = ElementTree.parse(path)
    root = et.getroot()
    for export in root.findall('export'):
        to_remove = []
        for child in export:
            if child.tag not in ['metapackage', 'rosdoc', 'deprecated']:
                to_remove.append(child)
        for child in to_remove:
            export.remove(child)
    et.write(path)


def replace_catkin_cmake_files(catkin_packages):
    for path in catkin_packages.values():
        #Replace cmake files with custom version
        cmake_file = os.path.join(path, "CMakeLists.txt")
        if os.path.isfile(cmake_file):
            with open(cmake_file, 'w') as f:
                f.write(catkin_cmake_file)

        #Remove export lines from manifest files
        pkg_file = os.path.join(path, "package.xml")
        if os.path.isfile(pkg_file):
            remove_export_tags(pkg_file)


def replace_manifest_cmake_files(manifest_packages):
    for path in manifest_packages.values():
        #Remove export lines from manifest files
        pkg_file = os.path.join(path, "manifest.xml")
        if os.path.isfile(pkg_file):
            remove_export_tags(pkg_file)

        #Replace Cmake files with custom version
        cmake_file = os.path.join(path, "CMakeLists.txt")
        if os.path.isfile(cmake_file):
            catkin = False
            genaction = genmsg = gensrv = ''
            #Only build targets that should be built
            with open(cmake_file, 'r') as f:
                read_file = f.read()
                if 'catkin_project' in read_file:
                    catkin = True
                if 'genaction' in read_file:
                    genaction = 'genaction()'
                if 'rosbuild_genmsg' in read_file:
                    genmsg = 'rosbuild_genmsg()'
                if 'rosbuild_gensrv' in read_file:
                    gensrv = 'rosbuild_gensrv()'

            #There's nothing to do really for catkin on fuerte, we'll just skip
            if not catkin:
                with open(cmake_file, 'w') as f:
                    if genaction:
                        build_file = manifest_cmake_file + actionlib_msgs_include + manifest_build_targets.format(genaction=genaction, genmsg=genmsg, gensrv=gensrv)
                    else:
                        build_file = manifest_cmake_file + manifest_build_targets.format(genaction=genaction, genmsg=genmsg, gensrv=gensrv)
                    f.write(build_file)


def generate_messages_catkin(env):
    try:
        targets = check_output("make help", env).split('\n')
    except BuildException:
        return

    genpy_targets = [t.split()[1] for t in targets if t.endswith("genpy")]
    print genpy_targets
    for t in genpy_targets:
        call("make %s" % t, env)


def generate_messages_dry(env, name, messages, services):
    try:
        targets = check_output("make help", env).split('\n')
    except BuildException:
        return

    if [t for t in targets if t.endswith("ROSBUILD_genaction_msgs")]:
        call("make ROSBUILD_genaction_msgs", env)

    if [t for t in targets if t.endswith("rospack_genmsg")] and messages:
        call("make rospack_genmsg", env)
        print "Generated messages for %s" % name

    if [t for t in targets if t.endswith("rospack_gensrv")] and services:
        call("make rospack_gensrv", env)
        print "Generated services for %s" % name


def build_repo_messages_catkin_stacks(stacks, ros_distro, local_install_path):
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)

    #Make sure to create the local install path if it doesn't exist
    if os.path.exists(local_install_path):
        shutil.rmtree(local_install_path)
    os.makedirs(local_install_path)
    os.makedirs(os.path.join(local_install_path, 'lib/python2.7/dist-packages'))
    os.makedirs(os.path.join(local_install_path, 'lib/python2.6/dist-packages'))
    os.makedirs(os.path.join(local_install_path, 'share'))
    os.makedirs(os.path.join(local_install_path, 'bin'))
    build_errors = []

    for stack, path in stacks.iteritems():
        #check to see if the stack is catkin or not
        cmake_file = os.path.join(path, 'CMakeLists.txt')

        catkin = False
        #If a CMakeLists.txt file doesn't exist, we assume the stack is not catkinized
        if os.path.isfile(cmake_file):
            with open(cmake_file, 'r') as f:
                read_file = f.read()
                if 'catkin_stack' in read_file:
                    catkin = True

        #if the stack is a catkin stack, we want to build and install it locally
        if catkin:
            old_dir = os.getcwd()
            os.chdir(path)
            if not os.path.exists('build'):
                os.makedirs('build')
            os.chdir('build')
            try:
                call("cmake -DCMAKE_INSTALL_PREFIX:PATH=%s .." % local_install_path, ros_env)
                call("make", ros_env)
                call("make install", ros_env)
            except BuildException as e:
                print "FAILED TO BUILD %s, messages for this package cannot be generated." % (stack)
                print "Failure on %s, with env path %s" % (stack, ros_env)
                print "Exception: %s" % e
                build_errors.append(stack)
            os.chdir(old_dir)

    #We'll throw the appropriate stuff on our python path
    export = "export PYTHONPATH=%s/lib/python2.7/dist-packages:$PYTHONPATH" % local_install_path
    return (export, build_errors)


def build_repo_messages_manifest(manifest_packages, build_order, ros_distro):
    #Now, we go through all of our manifest packages and try to generate
    #messages, or add them to the pythonpath if they turn out to be catkin
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)
    path_string = ''
    build_errors = []

    #Make sure to build with our special cmake file to only do message generation
    replace_manifest_cmake_files(manifest_packages)

    #Make sure to build in dependency order
    for name in build_order:
        if not name in manifest_packages or name in ['rosdoc_lite', 'catkin']:
            continue

        path = manifest_packages[name]

        cmake_file = os.path.join(path, 'CMakeLists.txt')
        if os.path.isfile(cmake_file):
            catkin = False
            messages = False
            services = False
            #Check to see whether the package is catkin or not
            #Also check whether we actually need to build messages
            #and services since rosbuild creates the build targets
            #no matter what
            with open(cmake_file, 'r') as f:
                read_file = f.read()
                if 'catkin_project' in read_file:
                    catkin = True
                if 'rosbuild_genmsg' in read_file:
                    messages = True
                if 'rosbuild_gensrv' in read_file:
                    services = True

            #If it is catkin, then we'll do our best to put the right things on the python path
            #TODO: Note that this will not generate messages, we can try to put this in later
            #but fuerte catkin makes it kind of hard to do correctly
            if catkin:
                print "Not doing anything for catkin package"
                #print "Creating an export line that guesses the appropriate python paths for each package"
                #print "WARNING: This will not properly generate message files within this repo for python documentation."
                #if os.path.isdir(os.path.join(path, 'src')):
                #    path_string = "%s:%s" %(os.path.join(path, 'src'), path_string)

            #If it's not catkin, then we'll generate python messages
            else:
                old_dir = os.getcwd()
                os.chdir(path)
                if not os.path.exists('build'):
                    os.makedirs('build')
                os.chdir('build')
                ros_env['ROS_PACKAGE_PATH'] = '%s:%s' % (path, ros_env['ROS_PACKAGE_PATH'])
                try:
                    call("cmake ..", ros_env)
                    generate_messages_dry(ros_env, name, messages, services)
                except BuildException as e:
                    print "FAILED TO CALL CMAKE ON %s, messages for this package cannot be generated." % (name)
                    print "Are you sure that the package specifies its dependencies correctly?"
                    print "Failure on %s, with env path %s" % (name, ros_env)
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


def build_repo_messages(catkin_packages, docspace, ros_distro):
    #we'll replace cmake files with our own since we only want to do message generation
    replace_catkin_cmake_files(catkin_packages)
    build_errors = []
    #For groovy, this isn't too bad, we just set up a workspace
    old_dir = os.getcwd()
    repo_devel = os.path.join(docspace, 'build_repo')
    if not os.path.exists(repo_devel):
        os.makedirs(repo_devel)
    os.chdir(repo_devel)
    print "Removing the CMakeLists.txt file generated by rosinstall"
    os.remove(os.path.join(docspace, 'CMakeLists.txt'))
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)
    print "Calling cmake..."
    call("catkin_init_workspace %s" % docspace, ros_env)
    try:
        call("cmake ..", ros_env)
        ros_env = get_ros_env(os.path.join(repo_devel, 'devel/setup.bash'))
        generate_messages_catkin(ros_env)
        source = 'source %s' % (os.path.abspath(os.path.join(repo_devel, 'devel/setup.bash')))
    except BuildException as e:
        print "FAILED TO CALL CMAKE ON CATKIN REPOS"
        print "There will be no messages in documentation and some python docs may fail"
        print "Exception: %s" % e
        source = ''
        build_errors.append("catkin_workspace for repository")
    os.chdir(old_dir)
    return (source, build_errors)
