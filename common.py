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



def apt_get_install(pkgs, rosdep):
    if len(pkgs) > 0:
        call("apt-get install --yes %s"%(' '.join(rosdep.to_aptlist(pkgs))))
    else:
        print "Not installing anything from apt right now."



## {{{ http://code.activestate.com/recipes/577187/ (r9)
class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""
    def __init__(self, tasks):
        Thread.__init__(self)
        self.tasks = tasks
        self.daemon = True
        self.start()

    def run(self):
        while True:
            func, args, kargs = self.tasks.get()
            try: func(*args, **kargs)
            except Exception, e: print e
            self.tasks.task_done()

class ThreadPool:
    """Pool of threads consuming tasks from a queue"""
    def __init__(self, num_threads):
        self.tasks = Queue(num_threads)
        for _ in range(num_threads): Worker(self.tasks)

    def add_task(self, func, *args, **kargs):
        """Add a task to the queue"""
        self.tasks.put((func, args, kargs))

    def wait_completion(self):
        """Wait for completion of all the tasks in the queue"""
        self.tasks.join()



class DevelDistro:
    def __init__(self, name):
        url = urllib2.urlopen('https://raw.github.com/ros/rosdistro/master/releases/%s-devel.yaml'%name)
        distro = yaml.load(url.read())['repositories']
        self.repositories = {}
        for name, data in distro.iteritems():
            repo = DevelDistroRepo(name, data)
            self.repositories[name] = repo



class DevelDistroRepo:
    def __init__(self, name, data):
        self.name = name
        self.type = data['type']
        self.url = data['url']
        self.version = None
        if data.has_key('version'):
            self.version = data['version']

    def get_rosinstall(self):
        if self.version:
            return yaml.dump([{self.type: {'local-name': self.name, 'uri': '%s'%self.url, 'version': '%s'%self.version}}], default_style=False)
        else:
            return yaml.dump([{self.type: {'local-name': self.name, 'uri': '%s'%self.url}}], default_style=False)




class RosDistro:
    def __init__(self, name, prefetch_dependencies=False, prefetch_upstream=False):
        url = urllib2.urlopen('https://raw.github.com/ros/rosdistro/master/releases/%s.yaml'%name)
        distro = yaml.load(url.read())['repositories']
        self.repositories = {}
        self.packages = {}
        for repo_name, data in distro.iteritems():
            distro_pkgs = []
            url = data['url']
            version = data['version']
            if not data.has_key('packages'):   # support unary disto's
                data['packages'] = {repo_name: ''}
            for pkg_name in data['packages'].keys():
                pkg = RosDistroPackage(pkg_name, repo_name, url, version)
                distro_pkgs.append(pkg)
                self.packages[pkg_name] = pkg
            self.repositories[repo_name] = RosDistroRepo(repo_name, url, version, distro_pkgs)

        # prefetch package dependencies
        if prefetch_dependencies:
            self.prefetch_package_dependencies()

        # prefetch distro upstream
        if prefetch_upstream:
            self.prefetch_repository_upstream()



    def prefetch_package_dependencies(self):
        threadpool = ThreadPool(5)

        # add jobs to queue
        for name, pkg in self.packages.iteritems():
            threadpool.add_task(pkg.get_dependencies)

        # wait for queue to be finished
        failed = []
        print "Waiting for prefetching of package dependencies to finish"
        for name, pkg in self.packages.iteritems():
            count = 0
            while not pkg.depends1:
                time.sleep(0.1)
                count += 1
                if not count%10:
                    print "Still waiting for package %s to complete"%pkg.name
            if pkg.depends1 == "Failure":
                print "Failed to complete package %s"%pkg.name
                failed.append(name)

        # remove failed packages
        print "Could not fetch dependencies of the following packages from githib; pretending they do not exist: %s"%', '.join(failed)
        for f in failed:
            if self.repositories.has_key(self.packages[f].repo):
                self.repositories.pop(self.packages[f].repo)
            self.packages.pop(f)
        print "All package dependencies have been prefetched"


    def prefetch_repository_upstream(self):
        threadpool = ThreadPool(5)

        # add jobs to queue
        for name, repo in self.repositories.iteritems():
            threadpool.add_task(repo.get_upstream)

        # wait for queue to be finished
        for name, repo in self.repositories.iteritems():
            while not repo.upstream:
                time.sleep(0.1)


    def depends1(self, package, dep_type):
        if type(package) == list:
            res = []
            for p in package:
                res.append(self.depends1(p, dep_type))
            return res
        else:
            dep_list = dep_type if type(dep_type) == list else [dep_type]
            for dt in dep_list:
                d = self.packages[package].get_dependencies()[dt]
            print "%s depends on %s"%(package, str(d))
            return d



    def depends(self, package, dep_type, res=[]):
        if type(package) == list:
            for p in package:
                self.depends(p, dep_type, res)
        else:
            for d in self.depends1(package, dep_type):
                if d in self.packages and not d in res:
                    res.append(d)
                    self.depends(d, dep_type, res)
        return res


    def depends_on1(self, package, dep_type):
        if type(package) == list:
            res = []
            for p in package:
                res.append(self.depends_on1(p, dep_type))
            return res
        else:
            depends_on1 = []
            for name, pkg in self.packages.iteritems():
                dep_list = dep_type if type(dep_type) == list else [dep_type]
                for dt in dep_list:
                    if package in pkg.get_dependencies()[dt]:
                        depends_on1.append(name)
            return depends_on1


    def depends_on(self, package, dep_type, res=[]):
        if type(package) == list:
            for p in package:
                self.depends_on(p, dep_type, res)
        else:
            for d in self.depends_on1(package, dep_type):
                if d in self.packages and not d in res:
                    res.append(d)
                    self.depends_on(d, dep_type, res)
        return res






class RosDistroRepo:
    def __init__(self, name, url, version, pkgs):
        self.name = name
        self.url = url
        if version:
            self.version = version.split('-')[0]
        else:
            self.version = version
        self.pkgs = pkgs
        self.upstream = None

    def get_rosinstall_release(self, version=None):
        rosinstall = ""
        for p in self.pkgs:
            rosinstall += p.get_rosinstall_release(version)
        return rosinstall

    def get_rosinstall_latest(self):
        rosinstall = ""
        for p in self.pkgs:
            rosinstall += p.get_rosinstall_latest()
        return rosinstall

    def get_upstream(self):
        if not self.upstream:
            url = self.url
            url = url.replace('.git', '/bloom/bloom.conf')
            url = url.replace('git://', 'https://')
            url = url.replace('https://', 'https://raw.')
            retries = 5
            while not self.upstream and retries > 0:
                res = {'version': ''}
                repo_conf = urllib2.urlopen(url).read()
                for r in repo_conf.split('\n'):
                    conf = r.split(' = ')
                    if conf[0] == '\tupstream':
                        res['url'] = conf[1]
                    if conf[0] == '\tupstreamtype':
                        res['type'] = conf[1]
                    if conf[0] == '\tupstreamversion':
                        res['version'] = conf[1]
                if res['version'] == '':
                    if res['type'] == 'git':
                        res['version'] = 'master'
                    if res['type'] == 'hg':
                        res['version'] = 'default'
                self.upstream = res

                # fix for svn trunk
                if res['type'] == 'svn':
                    res['url'] += "/trunk"
        return self.upstream


class RosDistroPackage:
    def __init__(self, name, repo, url, version):
        self.name = name
        self.repo = repo
        self.url = url
        if version:
            self.version = version.split('-')[0]
            self.depends1 = None
        else:
            self.version = version
            self.depends1 = {'build': [], 'test': [], 'run': []}

    def get_dependencies(self):
        if self.depends1:
            return self.depends1

        url = self.url
        url = url.replace('.git', '/release/%s/%s/package.xml'%(self.name, self.version))
        url = url.replace('git://', 'https://')
        url = url.replace('https://', 'https://raw.')
        retries = 5
        while retries > 0:
            try:
                package_xml = urllib2.urlopen(url).read()
                append_pymodules_if_needed()
                from catkin_pkg import package as catkin_pkg
                pkg = catkin_pkg.parse_package_string(package_xml)
                self.depends1 = {'build': [d.name for d in pkg.build_depends], 'test':  [d.name for d in pkg.test_depends], 'run': [d.name for d in pkg.run_depends]}
                return self.depends1
            except:
                print "!!!! Failed to download package.xml for package %s at url %s"%(self.name, url)
                time.sleep(2.0)
                retries -= 1

        if not self.depends1:
            self.depends1 = "Failure"
            raise BuildException("Failed to get package.xml at %s"%url)





    def get_rosinstall_release(self, version=None):
        if not version:
            version = self.version
        return yaml.safe_dump([{'git': {'local-name': self.name, 'uri': self.url, 'version': '?'.join(['release', self.name, version])}}],
                              default_style=False).replace('?', '/')

    def get_rosinstall_latest(self):
        return yaml.dump([{'git': {'local-name': self.name, 'uri': self.url, 'version': '/'.join(['release', self.name])}}],
                         default_style=False)





class AptDepends:
    def __init__(self, ubuntudistro, arch, shadow=True):
        if shadow:
            url = urllib2.urlopen('http://packages.ros.org/ros-shadow-fixed/ubuntu/dists/%s/main/binary-%s/Packages'%(ubuntudistro, arch))
        else:
            url = urllib2.urlopen('http://packages.ros.org/ros/ubuntu/dists/%s/main/binary-%s/Packages'%(ubuntudistro, arch))
        self.dep = {}
        package = None
        for l in url.read().split('\n'):
            if 'Package: ' in l:
                package = l.split('Package: ')[1]
            if 'Depends: ' in l:
                if not package:
                    raise BuildException("Found 'depends' but not 'package' while parsing the apt repository index file")
                self.dep[package] = [d.split(' ')[0] for d in (l.split('Depends: ')[1].split(', '))]
                package = None

    def has_package(self, package):
        return package in self.dep

    def depends1(self, package):
        return self.depends(package, one=True)

    def depends(self, package, res=[], one=False):
        if package in self.dep:
            for d in self.dep[package]:
                if not d in res:
                    res.append(d)
                if not one:
                    self.depends(d, res, one)
        return res

    def depends_on1(self, package):
        return self.depends_on(package, one=True)

    def depends_on(self, package, res=[], one=False):
        for p, dep in self.dep.iteritems():
            if package in dep:
                if not p in res:
                    res.append(p)
                if not one:
                    self.depends_on(p, res, one)
        return res



class RosDepResolver:
    def __init__(self, ros_distro):
        self.r2a = {}
        self.a2r = {}
        self.env = os.environ
        self.env['ROS_DISTRO'] = ros_distro

        print "Ininitalize rosdep database"
        call("apt-get install --yes lsb-release python-rosdep")
        call("rosdep init", self.env)
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

def get_nonlocal_dependencies(catkin_packages, stacks, manifest_packages):
    append_pymodules_if_needed()
    from catkin_pkg import packages
    import rospkg

    depends = []
    #First, we build the catkin deps
    for name, path in catkin_packages.iteritems():
        pkg_info = packages.parse_package(path)
        depends.extend([d.name \
                        for d in pkg_info.build_depends + pkg_info.test_depends + pkg_info.run_depends \
                        if not d.name in catkin_packages and not d.name in depends])

    #Next, we build the manifest deps for stacks
    for name, path in stacks.iteritems():
        stack_manifest = rospkg.parse_manifest_file(path, rospkg.STACK_FILE)
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
        for d in pkg_info.build_depends + pkg_info.test_depends + pkg_info.run_depends:
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
    local_packages = pkgs.keys()
    if len(pkgs) > 0:
        print "In folder %s, found packages %s"%(source_folder, ', '.join(local_packages))
    else:
        raise BuildException("Found no packages in folder %s. Are you sure your packages have a packages.xml file?"%source_folder)

    depends = []
    for name, pkg in pkgs.iteritems():
        if build_depends:
            for d in pkg.build_depends:
                if not d.name in depends and not d.name in local_packages:
                    depends.append(d.name)
        if test_depends:
            for d in pkg.test_depends:
                if not d.name in depends and not d.name in local_packages:
                    depends.append(d.name)

    return depends



class BuildException(Exception):
    def __init__(self, msg):
        self.msg = msg
