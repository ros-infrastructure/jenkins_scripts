#!/usr/bin/env python
from __future__ import with_statement

from optparse import OptionParser
import sys, os
import shutil
# TODO: convert everythin to urllib2
import urllib
import urllib2
from subprocess import Popen, PIPE, call, check_call, CalledProcessError
import stat
import rospkg

NAME='hudson_helper'

if 'HUDSON_DEBUG' in os.environ and os.environ['HUDSON_DEBUG'] == '1':
  DEBUG = True
  print >> sys.stderr, '[%s] debug mode'%(NAME)
else:
  DEBUG = False
  print >> sys.stderr, '[%s] release mode'%(NAME)

# This URI can change over time as they make new releases.
COVMONSTER_URI = 'http://code.ros.org/svn/ros/installers/trunk/hudson/covmonster.py'
ATABLE_URI = 'http://code.ros.org/svn/ros/installers/trunk/hudson/atable.cst' 
ROSDEP_PY_URI = 'https://code.ros.org/svn/ros/installers/trunk/rosdeb/rosdep.py'
BUILD_DEBS_PY_URI = 'https://code.ros.org/svn/ros/installers/trunk/rosdeb/build_debs.py'
REROOT_PY_URI = 'https://code.ros.org/svn/ros/installers/trunk/rosdeb/reroot.py'

# When passed --stack-test=foo, we use these URIs to assemble a working
# copy for testing the foo stack.
SVN_URIS = {
 'ros-pkg' : 'https://code.ros.org/svn/ros-pkg',
 'wg-ros-pkg' : 'https://code.ros.org/svn/wg-ros-pkg'
}
SVN_LATEST_PATH = 'externals/latest'
SVN_EXTERNALS_PATH = 'externals/distro'
SVN_EXTERNALS_SUFFIX = 'all'
SVN_STACKS_PATH = 'stacks'
SVN_TRUNK_PATH = 'trunk'
ROS_STACK_URI = 'https://code.ros.org/svn/ros/stacks/ros/tags'
EMAIL_FROM_ADDR = 'ROS on-demand build <noreply@willowgarage.com>'

# Where we wish to eventually install a .deb
BUILDDEB_INSTALL_PATH = '/opt/ros/wg-all'

dummy_test_results_simple = """<?xml version="1.0" encoding="utf-8"?><testsuite name="no_tests_run" tests="0" errors="0" failures="0" time="0.0">  <system-out><![CDATA[]]></system-out>  <system-err><![CDATA[]]></system-err></testsuite>
"""

dummy_test_results_simple = """<?xml version="1.0" encoding="utf-8"?><testsuite name="dummy.TEST-test_dummy" tests="1" errors="0" failures="0" time="0.037">  <testcase classname="dummy.TEST-test_dummy.NotTested" name="dummy.test_dummy/NotTested" time="0.0">
  </testcase>  <system-out><![CDATA[]]></system-out>  <system-err><![CDATA[]]></system-err></testsuite>"""



# Temporary paste-in from roslib
def list_pkgs(pkg_dirs):
    packages = []
    for pkgRoot in pkg_dirs:
        for dir, dirs, files in os.walk(pkgRoot, topdown=True):
            if 'manifest.xml' in files:
                package = os.path.basename(dir)
                if package not in packages:
                  packages.append(package)
                del dirs[:]
            elif 'rospack_nosubdirs' in files:
                del dirs[:]
            #small optimization
            elif '.svn' in dirs:
                dirs.remove('.svn')
            elif '.git' in dirs:
                dirs.remove('.git')
    return packages

def svn_co(uri, wc_name, override_debug=False):
    svn_cmd = ['svn', 'co', uri, wc_name]
    print >> sys.stderr, '[%s] %s'%(NAME,svn_cmd)
    if DEBUG and not override_debug:
        return True
    # Call twice, with an rm in-between, to work around cases where a
    # previously unversioned file got checked in.
    if call(svn_cmd) == 0:
        return True
    else:
        if os.path.exists(wc_name):
            shutil.rmtree(wc_name)
            if call(svn_cmd) == 0:
                return True
    return False

def send_mail(from_addr, to_addrs, subject, text):
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(text)
    msg['From'] = from_addr
    msg['To'] = to_addrs
    msg['Subject'] = subject

    s = smtplib.SMTP('pub1.willowgarage.com')
    print >> sys.stderr, '[%s] Sending mail to %s'%(NAME,to_addrs)
    s.sendmail(msg['From'], [msg['To']], msg.as_string())
    s.quit()
                
class HudsonHelper:

    def __init__(self, argv):
        self._parse_args(argv)

    def _parse_args(self, argv):
        parser = OptionParser(usage="usage: %prog [options] <cmd>", prog=NAME)
        parser.add_option("--pkg", action="append",
                          dest="pkgs", default=[],
                          help="packages to build")
        parser.add_option("--pkg-test", action="append",
                          dest="pkgs_test", default=[],
                          help="packages to test")
        parser.add_option("--repo", action="append", nargs=2,
                          dest="repos", default=[],
                          help="repo to checkout / build")
        parser.add_option("--repo-test", action="append", nargs=2,
                          dest="repos_test", default=[],
                          help="repo to checkout / build, and test")
        parser.add_option("--dir", action="append", nargs=1,
                          dest="dirs", default=[],
                          help="directory to append to RPP")
        parser.add_option("--dir-test", action="append", nargs=1,
                          dest="dirs_test", default=[],
                          help="directory to append to RPP, and test in")
        parser.add_option("--test-label", action="store",
                          dest="test_label", default="hudson",
                          help="value to be set via ROS_BUILD_TEST_LABEL")
        parser.add_option("--email", action="store",
                          dest="email", default=None,
                          help="email address to send results to")
        parser.add_option("--debug", action="store_true",
                          dest="debug", default=False,
                          help="debugging mode")
        parser.add_option("--post-processor", action="append",
                          dest="post_processors", default=[],
                          help="program(s) to run at the end of the build")
        parser.add_option("-k", "--keep-going", action="store_true",
                          dest="keep_going", default=False,
                          help="continue in the face of build failures")
        (options, args) = parser.parse_args(argv)
    
        if len(args) < 2:
            parser.error('must specify command')
        self.cmd = args[1]
    
        if options.debug:
            global DEBUG
            DEBUG = True

        self.post_processors = options.post_processors
        self.keep_going = options.keep_going
    
        if (len(options.repos) + 
            len(options.repos_test) +
            len(options.dirs) + 
            len(options.dirs_test) +
            len(options.pkgs) + 
            len(options.pkgs_test)) == 0:
            parser.error("nothing to do; must specify at least one of --distro, --repo, --dir, --pkg, --distro-test, --repo-test, --pkg-test, --dir-test, or --stack-data")
    
        self.repos = []
        self.repos_test = []
    
        for r in options.repos:
            self.repos.append((r[1], r[0]))
        for r in options.repos_test:
            self.repos_test.append((r[1], r[0]))
            self.repos.append((r[1], r[0]))

        # NOTE: the following addition puts directories specified by --dir-test
        # ahead of those specified by --dir.  This is correct for ondemand test
        # builds of stack/trunk against */latest, but will not be right in
        # general.
        self.dirs = options.dirs_test + options.dirs
        self.dirs_test = options.dirs_test
    
        self.test_label = options.test_label
        self.pkgs = options.pkgs
        self.pkgs_test = options.pkgs_test
        self.email = options.email

        self.distro = None
	

    def main(self):
	stderrs = []
        if self.cmd in ['checkout', 'co', 'update', 'up']:
            for k, url in self.repos:
                v = Popen(['svn', 'co', url, k], stdout=sys.stdout, stdin=sys.stdin, stderr=sys.stderr).communicate()
        elif self.cmd in ['ci', 'commit']:
            print >> sys.stderr, "commit is disabled for rosorg-svn command. Please cd to the appropriate directory where changes are and used svn normally"
        elif self.cmd == 'urls':
            for k, url in self.repos:
                print url
        elif self.cmd == 'build':
            self.build()
        else:
            for k, url in self.repos:
                if os.path.isdir(k):
                    v = Popen(['svn', cmd]+sys.argv[2:], cwd=k, stdout=PIPE, stderr=PIPE).communicate()
                    if v[0]:
                        print "-- [%s] -------"%k
                        print v[0]
                    stderrs.append(v[1])
            stderrs = [s for s in stderrs if s.strip()]
            if stderrs:
                print "WARNING: svn reported the following errors:"
                print "\n----\n".join(stderrs)
	
    def build(self):
	# Hudson sets the WORKSPACE env var
        workspace = os.environ['STACK_BUILD_DIR']
	    #workspace = '/tmp'
        os.environ['JOB_NAME'] = 'build'

        ros_test_results_dir = rospkg.get_test_results_dir()
        print '1. Test results dir is set to %s'%ros_test_results_dir

        # Blow away old ~/.ros content. self.dotrosname is used at the end
        # of this method, for tarring up the result of this run.
        self.dotrosname = os.path.join(workspace, '.ros')
	if os.path.isdir(self.dotrosname):
            try:
                shutil.rmtree(self.dotrosname)
            except OSError, e:
        	# Ignore this; it's usually a stale NFS handle.
                pass
        elif os.path.isfile(self.dotrosname):
            os.unlink(self.dotrosname)
        if not os.path.isdir(self.dotrosname):
            os.makedirs(self.dotrosname)
	self.rosmake_path = 'rosmake'

        local_paths = []
        for r in self.repos:
            local_paths.append(os.path.abspath(r[0]))
        for d in self.dirs:
            local_paths.append(os.path.abspath(d))
        if 'ROS_PACKAGE_PATH' in os.environ:
            # Prepend directories given on the command-line, on the
            # assumption that they are intended as overlays atop whatever
            # was in the environment already.
            ros_package_path = ':'.join(local_paths + [os.environ['ROS_PACKAGE_PATH']])
        else:
            ros_package_path = ':'.join(local_paths)
	    

        env_vars = os.environ.copy()
        # The JAVA_HOME setting is specific to Ubuntu.
        env_vars.update({'ROS_PACKAGE_PATH' : ros_package_path,
                         'ROSDEP_YES' : '1',
                         'ROS_LOG_DIR' : os.path.join(self.dotrosname, 'log'),
                         'ROS_TEST_RESULTS_DIR' : ros_test_results_dir,
                         'ROS_MASTER_URI' : 'http://localhost:11311',
                         'ROS_BUILD_TEST_LABEL' : self.test_label,
                         'ROBOT' : 'sim',
                         'JAVA_HOME' : '/usr/lib/jvm/java-6-openjdk/',
                         'DISPLAY' : ':0.0'})
	  
        print env_vars['ROS_PACKAGE_PATH']
       
	
        if 'SVN_REVISION' in env_vars:
            del env_vars['SVN_REVISION']

        failure = False
        test_failure = False
 
        ###########################################
        # suppress extra output
        self.extra_rosmake_args = ['--status-rate=0']

        ###########################################
        # rosmake build everything
        #output_dir = os.path.join(workspace, 'build_output')
        #output_dir = os.path.join(os.environ['PWD'], 'build_output')
        output_dir = os.path.join(workspace)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        # Create dummy result files, to avoid Groovy stack traces in
        # emails, #3214. The files will be closed because we don't save
        # the result from open().
        os.makedirs(output_dir)
        open(os.path.join(output_dir, 'buildfailures.txt'), 'w')
        open(os.path.join(output_dir, 'buildfailures-with-context.txt'), 'w')
	
        if (len(self.pkgs) + len(self.pkgs_test)) > 0:
          pkg_arg = self.pkgs + self.pkgs_test
        else:
          pkg_arg = ['-a']
        build_cmd = [self.rosmake_path, '-Vr', '--profile', '--skip-blacklist', '--output=%s'%output_dir] + self.extra_rosmake_args + pkg_arg
	
	
        # Temporary
        if os.uname()[0] == 'Darwin':
            build_cmd.append('--skip-blacklist-osx')
	
        try:
            print >> sys.stderr, '[%s] %s'%(NAME,build_cmd)
	    
            if not DEBUG:
                print "Run rosmake" 
                check_call(build_cmd, env=env_vars, stdout=sys.stdout, stdin=sys.stdin, stderr=sys.stderr)
        except (CalledProcessError, OSError), e:
            failure = True
            print >> sys.stderr, '[%s] Error in build step:%s'%(NAME,e)
            #assert False
            #assert false
            #if not self.keep_going:
            #    self.post_build(failure, test_failure, workspace)
	

if __name__ == '__main__':            
    hh = HudsonHelper(sys.argv)
    hh.main()


