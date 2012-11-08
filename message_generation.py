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
from common import call, get_ros_env, BuildException

catkin_cmake_file = """cmake_minimum_required(VERSION 2.8.3)
find_package(catkin_basic REQUIRED)
catkin_basic()"""

manifest_cmake_file = """cmake_minimum_required(VERSION 2.4.6)
include($ENV{ROS_ROOT}/core/rosbuild/rosbuild.cmake)
rosbuild_find_ros_package(actionlib_msgs)
include(${actionlib_msgs_PACKAGE_PATH}/cmake/actionbuild.cmake)
"""
manifest_build_targets = """
{genaction}
rosbuild_init()
{genmsg}
{gensrv}"""

def replace_catkin_cmake_files(catkin_packages):
    for pkg, path in catkin_packages.iteritems():
        cmake_file = os.path.join(path, "CMakeLists.txt")
        if os.path.isfile(cmake_file):
            with open(cmake_file, 'w') as f:
                f.write(catkin_cmake_file)

def replace_manifest_cmake_files(manifest_packages):
    for pkg, path in manifest_packages.iteritems():
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
                    build_file = manifest_cmake_file + manifest_build_targets.format(genaction=genaction, genmsg=genmsg, gensrv=gensrv)
                    print "Generated the following cmake file:\n%s" % build_file
                    f.write(build_file)


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
                try:
                    call("cmake ..", ros_env)
                    generate_messages_dry(ros_env, name)
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
    repo_develspace = os.path.join(docspace, 'build_repo')
    if not os.path.exists(repo_develspace):
        os.makedirs(repo_develspace)
    os.chdir(repo_develspace)
    print "Removing the CMakeLists.txt file generated by rosinstall"
    os.remove(os.path.join(docspace, 'CMakeLists.txt'))
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' %ros_distro)
    print "Calling cmake..."
    call("catkin_init_workspace %s"%docspace, ros_env)
    try:
        call("cmake ..", ros_env)
        ros_env = get_ros_env(os.path.join(repo_develspace, 'develspace/setup.bash'))
        generate_messages_catkin(ros_env)
        source = 'source %s' % (os.path.abspath(os.path.join(repo_develspace, 'develspace/setup.bash')))
    except BuildException as e:
        print "FAILED TO CALL CMAKE ON CATKIN REPOS"
        print "There will be no messages in documentation and some python docs may fail"
        print "Exception: %s" % e
        source = ''
        build_errors.append("catkin_workspace for repository")
    os.chdir(old_dir)
    return (source, build_errors)

