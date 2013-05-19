#!/usr/bin/env python

#!/usr/bin/env python
import os
import sys
import subprocess
import string
import fnmatch
import shutil
import optparse
from time import sleep
import rosdistro

def get_environment2():
    my_env = os.environ
    my_env['WORKSPACE'] = os.getenv('WORKSPACE', '')
    my_env['INSTALL_DIR'] = os.getenv('INSTALL_DIR', '')
    #my_env['HOME'] = os.getenv('HOME', '')
    my_env['HOME'] = os.path.expanduser('~')
    my_env['JOB_NAME'] = os.getenv('JOB_NAME', '')
    my_env['BUILD_NUMBER'] = os.getenv('BUILD_NUMBER', '')
    my_env['ROS_TEST_RESULTS_DIR'] = os.getenv('ROS_TEST_RESULTS_DIR', my_env['WORKSPACE']+'/test_results')
    my_env['PWD'] = os.getenv('WORKSPACE', '')
    #my_env['ROS_PACKAGE_MIRROR'] = 'http://packages.ros.org/ros/ubuntu'
    my_env['ROS_PACKAGE_MIRROR'] = 'http://apt-mirror/packages/ros'


def main():
    # parse command line options
    #(options, args) = get_options(['rosdistro', 'buildsystem'], ['repeat', 'source-only'])
    parser = optparse.OptionParser()
    (options, args) = parser.parse_args()
    if not options:
       return -1

    platform = args[0]   # e.g. precise
    arch = args[1]       # e.g. amd64
    email = args[2]      # e.g. best_email@ever.com
    ros_distro = args[3] # e.g. groovy
    
    # parse the rosdistro file
    print "Parsing rosdistro file for %s"%ros_distro
    distro = rosdistro.RosDistro(ros_distro)
    print "Parsing devel file for %s"%ros_distro
    devel = rosdistro.DevelDistro(ros_distro)
    env = get_environment2()

    try:
        for stack in distro.get_repositories():
           print 'Analyzing stack %s'%stack
	   h = subprocess.Popen(('run_chroot_jenkins_now %s %s %s metrics %s %s wet'%(platform, arch, email, ros_distro,stack)).split(' '),env=env)
           h.communicate()
    except Exception, ex:
        print "%s. Check the console output for test failure details."%ex
        traceback.print_exc(file=sys.stdout)
        raise ex

if __name__ == '__main__':
    main()
