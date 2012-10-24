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
import urllib
import os
import shutil
from common import *
import subprocess
import time

class TagsDb(object):
    def __init__(self, distro_name, workspace):
        self.workspace = workspace
        self.distro_name = distro_name
        self.path  = os.path.abspath(os.path.join(self.workspace, 'rosdoc_tag_index'))
        if os.path.exists(self.path):
            shutil.rmtree(self.path)

        command = ['bash', '-c', 'export GIT_SSH="%s/jenkins_scripts/git_ssh" \
                   && git clone git@github.com:ros-infrastructure/rosdoc_tag_index.git %s' \
                   %(workspace, self.path) ]

        proc = subprocess.Popen(command)
        proc.communicate()

        self.tags = self.read_folder('tags')

        self.forward_deps = self.read_folder('deps')
        self.build_reverse_deps()

        self.metapackages = self.read_folder('metapackages')
        self.build_metapackage_index()

    #Turn a folder of files into a dict
    def read_folder(self, folder_name):
        folder_dict = {}
        folder = os.path.join(self.path, self.distro_name, folder_name)
        if os.path.exists(folder):
            for key in os.listdir(folder):
                with open(os.path.join(folder, key), 'r') as f:
                    folder_dict[key] = yaml.load(f)
        return folder_dict

    #Write a dict to a file with an entry per key
    def write_folder(self, folder_name, folder_dict):
        folder = os.path.join(self.path, self.distro_name, folder_name)

        #Make sure to create the directory we want to write to if it doesn't exist
        if not os.path.isdir(folder):
            os.makedirs(folder)

        for key, values in folder_dict.iteritems():
            with open(os.path.join(folder, key), 'w') as f:
                yaml.safe_dump(values, f)
            call("git add %s" % os.path.join(folder, key))

    def build_metapackage_index(self):
        #Build reverse dependencies
        self.metapackage_index = {}
        for package, deps in self.metapackages.iteritems():
            for dep in deps:
                self.metapackage_index.setdefault(dep, []).append(package)

    def build_reverse_deps(self):
        #Build reverse dependencies
        self.reverse_deps = {}
        for package, deps in self.forward_deps.iteritems():
            for dep in deps:
                self.reverse_deps.setdefault(dep, []).append(package)

    def has_tags(self, key):
        return key in self.tags

    def get_tags(self, key):
        return self.tags[key]

    def set_tags(self, key, tags):
        self.tags[key] = tags

    def has_reverse_deps(self, key):
        return key in self.reverse_deps

    def get_reverse_deps(self, key):
        return self.reverse_deps[key]

    def add_forward_deps(self, key, deps):
        self.forward_deps[key] = deps
        self.build_reverse_deps()

    def has_metapackages(self, key):
        return key in self.metapackage_index

    def get_metapackages(self, key):
        return self.metapackage_index[key]

    def set_metapackage_deps(self, key, deps):
        self.metapackages[key] = deps
        self.build_metapackage_index()

    #Write new tag locations for a list of packages
    def commit_db(self):
        self.write_folder('tags', self.tags)
        self.write_folder('deps', self.forward_deps)
        self.write_folder('metapackages', self.metapackages)

        old_dir = os.getcwd()
        os.chdir(self.path)
        print "Commiting changes to tags and deps lists...."
        command = ['git', 'commit', '-a', '-m', 'Updating tags and deps lists for %s' % (self.distro_name)]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE)

        env = os.environ
        env['GIT_SSH'] = "%s/jenkins_scripts/git_ssh" % self.workspace

        #Have some tolerance for things commiting to the db at the same time
        num_retries = 3
        i = 0
        while True:
            try:
                call("git fetch origin", env)
                call("git merge origin/master", env)
                call("git push origin master", env)
            except BuildException as e:
                print "Failed to fetch and merge..."
                if i >= num_retries:
                    raise e
                time.sleep(2)
                i += 1
                print "Trying again attempt %d of %d..." % (i, num_retries)
                continue

            break

        os.chdir(old_dir)
