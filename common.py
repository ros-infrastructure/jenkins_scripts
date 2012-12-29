import urllib2
import os
import subprocess
import sys
import fnmatch
import yaml
import threading
import time
from Queue import Queue
from threading import Thread

def append_pymodules_if_needed():
    #TODO: This is a hack, in the chroot, the default python path does not
    if not os.path.abspath("/usr/lib/pymodules/python2.7") in sys.path:
        sys.path.append("/usr/lib/pymodules/python2.7")



def apt_get_update(sudo=False):
    if not sudo:
        call("apt-get update")
    else:
        call("sudo apt-get update")        


def apt_get_install(pkgs, rosdep=None, sudo=False):
    cmd = "apt-get install --yes "
    if sudo:
        cmd = "sudo " + cmd

    if len(pkgs) > 0:
        if rosdep:
            call(cmd + ' '.join(rosdep.to_aptlist(pkgs)))
        else:
            call(cmd + ' '.join(pkgs))
    else:
        print "Not installing anything from apt right now."




class RosDepResolver:
    def __init__(self, ros_distro, sudo=False):
        self.r2a = {}
        self.a2r = {}
        self.env = os.environ
        self.env['ROS_DISTRO'] = ros_distro

        print "Ininitalize rosdep database"
        apt_get_install(['lsb-release', 'python-rosdep'], sudo=sudo)
        try:
            call("rosdep init", self.env)
        except:
            print "Rosdep is already initialized"
        call("rosdep update", self.env)

        print "Building dictionaries from a rosdep's db"
        raw_db = call("rosdep db", self.env, verbose=False).split('\n')

        for entry in raw_db:
            split_entry = entry.split(' -> ')
            if len(split_entry) < 2:
                continue
            ros_entry = split_entry[0]
            apt_entries = split_entry[1].split(' ')
            self.r2a[ros_entry] = apt_entries
            for a in apt_entries:
                self.a2r[a] = ros_entry

    def to_aptlist(self, ros_entries):
        res = []
        for r in ros_entries:
            for a in self.to_apt(r):
                if not a in res:
                    res.append(a)
        return res

    def to_ros(self, apt_entry):
        if not self.a2r.has_key(apt_entry):
            print "Could not find %s in rosdep keys. Rosdep knows about these keys: %s"%(apt_entry, ', '.join(self.a2r.keys()))
        return self.a2r[apt_entry]

    def to_apt(self, ros_entry):
        if not self.r2a.has_key(ros_entry):
            print "Could not find %s in keys. Have keys %s"%(ros_entry, ', '.join(self.r2a.keys()))
        return self.r2a[ros_entry]

    def has_ros(self, ros_entry):
        return ros_entry in self.r2a

    def has_apt(self, apt_entry):
        return apt_entry in self.a2r

class RosDep:
    def __init__(self, ros_distro):
        self.r2a = {}
        self.a2r = {}
        self.env = os.environ
        self.env['ROS_DISTRO'] = ros_distro

        # Initialize rosdep database
        print "Ininitalize rosdep database"
        call("apt-get install --yes lsb-release python-rosdep")
        call("rosdep init", self.env)
        call("rosdep update", self.env)

    def to_apt(self, r):
        if r in self.r2a:
            return self.r2a[r]
        else:
            res = call("rosdep resolve %s"%r, self.env).split('\n')
            if len(res) == 1:
                raise Exception("Could not resolve rosdep")
            a = call("rosdep resolve %s"%r, self.env).split('\n')[1]
            print "Rosdep %s resolved into %s"%(r, a)
            self.r2a[r] = a
            self.a2r[a] = r
            return a

    def to_stack(self, a):
        if not a in self.a2r:
            print "%s not in apt-to-rosdep cache"%a
        return self.a2r[a]




def copy_test_results(workspace, buildspace, errors=None, prefix='dummy'):
    print "Preparing xml test results"
    try:
        os.makedirs(os.path.join(workspace, 'test_results'))
        print "Created test results directory"
    except:
        pass
    os.chdir(os.path.join(workspace, 'test_results'))
    print "Copy all test results"
    count = 0
    for root, dirnames, filenames in os.walk(os.path.join(buildspace, 'test_results')):
        for filename in fnmatch.filter(filenames, '*.xml'):
            call("cp %s %s/test_results/"%(os.path.join(root, filename), workspace))
            count += 1
    if count == 0:
        print "No test results, so I'll create a dummy test result xml file, with errors %s" % errors
        with open(os.path.join(workspace, 'test_results/dummy.xml'), 'w') as f:
            if errors:
                f.write('<?xml version="1.0" encoding="UTF-8"?><testsuite tests="1" failures="0" time="1" errors="1" name="%s test"> <testcase name="%s rapport" classname="Results" /><testcase classname="%s_class" name="%sFailure"><error type="%sException">%s</error></testcase></testsuite>' % (prefix, prefix, prefix, prefix, prefix, errors))
            else:
                f.write('<?xml version="1.0" encoding="UTF-8"?><testsuite tests="1" failures="0" time="1" errors="0" name="dummy test"> <testcase name="dummy rapport" classname="Results" /></testsuite>')


def get_ros_env(setup_file):
    res = os.environ
    print "Retrieve the ROS build environment by sourcing %s"%setup_file
    command = ['bash', '-c', 'source %s && env'%setup_file]
    proc = subprocess.Popen(command, stdout = subprocess.PIPE)
    for line in proc.stdout:
        (key, _, value) = line.partition("=")
        res[key] = value.split('\n')[0]
    proc.communicate()
    if proc.returncode != 0:
        msg = "Failed to source %s"%setup_file
        print "/!\  %s"%msg
        raise BuildException(msg)
    return res


def call_with_list(command, envir=None, verbose=True):
    print "Executing command '%s'"%' '.join(command)
    helper = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, env=envir)
    res, err = helper.communicate()
    if verbose:
        print str(res)
    print str(err)
    if helper.returncode != 0:
        msg = "Failed to execute command '%s'"%command
        print "/!\  %s"%msg
        raise BuildException(msg)
    return res

def call(command, envir=None, verbose=True):
    return call_with_list(command.split(' '), envir, verbose)

def get_catkin_stack_deps(xml_path):
    import xml.etree.ElementTree as ET
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return list(set([d.text for d in root.findall('depends')] \
                 + [d.text for d in root.findall('build_depends')] \
                 + [d.text for d in root.findall('run_depends')]))

def get_nonlocal_dependencies(catkin_packages, stacks, manifest_packages):
    append_pymodules_if_needed()
    from catkin_pkg import packages
    import rospkg

    depends = []
    #First, we build the catkin deps
    for name, path in catkin_packages.iteritems():
        pkg_info = packages.parse_package(path)
        depends.extend([d.name \
                        for d in pkg_info.buildtool_depends + pkg_info.build_depends + pkg_info.test_depends + pkg_info.run_depends \
                        if not d.name in catkin_packages and not d.name in depends])

    #Next, we build the manifest deps for stacks
    for name, path in stacks.iteritems():
        stack_manifest = rospkg.parse_manifest_file(path, rospkg.STACK_FILE)
        if stack_manifest.is_catkin:
            depends.extend(get_catkin_stack_deps(os.path.join(path, 'stack.xml')))
        else:
            depends.extend([d.name \
                            for d in stack_manifest.depends + stack_manifest.rosdeps \
                            if not d.name in catkin_packages \
                            and not d.name in stacks \
                            and not d.name in depends])

    #Next, we build manifest deps for packages
    for name, path in manifest_packages.iteritems():
        pkg_manifest = rospkg.parse_manifest_file(path, rospkg.MANIFEST_FILE)
        depends.extend([d.name \
                        for d in pkg_manifest.depends + pkg_manifest.rosdeps \
                        if not d.name in catkin_packages \
                        and not d.name in stacks \
                        and not d.name in manifest_packages \
                        and not d.name in depends])


    return depends

def build_local_dependency_graph(catkin_packages, manifest_packages):
    append_pymodules_if_needed()
    from catkin_pkg import packages
    import rospkg

    depends = {}
    #First, we build the catkin dep tree
    for name, path in catkin_packages.iteritems():
        depends[name] = []
        pkg_info = packages.parse_package(path)
        for d in pkg_info.buildtool_depends + pkg_info.build_depends + pkg_info.test_depends + pkg_info.run_depends:
            if d.name in catkin_packages and d.name != name:
                depends[name].append(d.name)

    #Next, we build the manifest dep tree
    for name, path in manifest_packages.iteritems():
        manifest = rospkg.parse_manifest_file(path, rospkg.MANIFEST_FILE)
        depends[name] = []
        for d in manifest.depends + manifest.rosdeps:
            if (d.name in catkin_packages or d.name in manifest_packages) and d.name != name:
                depends[name].append(str(d.name))

    return depends

def reorder_paths(order, packages, paths):
    #we want to make sure that we can still associate packages with paths
    new_paths = []
    for package in order:
        old_index = [i for i, name in enumerate(packages) if package == name][0]
        new_paths.append(paths[old_index])

    return order, new_paths

def get_dependency_build_order(depends):
    import networkx as nx
    graph = nx.DiGraph()

    for name, deps in depends.iteritems():
        graph.add_node(name)
        graph.add_edges_from([(name, d) for d in deps])

    order = nx.topological_sort(graph)
    order.reverse()

    return order



def get_dependencies(source_folder, build_depends=True, test_depends=True):
    # get the dependencies
    print "Get the dependencies of source folder %s"%source_folder
    append_pymodules_if_needed()
    from catkin_pkg import packages
    pkgs = packages.find_packages(source_folder)
    local_packages = [p.split('/')[-1] for p in pkgs.keys()]
    if len(pkgs) > 0:
        print "In folder %s, found packages %s"%(source_folder, ', '.join(local_packages))
    else:
        raise BuildException("Found no packages in folder %s. Are you sure your packages have a packages.xml file?"%source_folder)

    depends = []
    for name, pkg in pkgs.iteritems():
        if build_depends:
            for d in pkg.build_depends + pkg.buildtool_depends:
                if not d.name in depends and not d.name in local_packages:
                    depends.append(d.name)
        if test_depends:
            for d in pkg.test_depends + pkg.run_depends:
                if not d.name in depends and not d.name in local_packages:
                    depends.append(d.name)

    return depends



class BuildException(Exception):
    def __init__(self, msg):
        self.msg = msg
