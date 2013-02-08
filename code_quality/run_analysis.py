#!/usr/bin/env python
import os
import sys
import subprocess
import string
import fnmatch
#import shutil
import optparse
from common import *
from time import sleep
import traceback


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
    
    return my_env


def remove(list1, list2):
    for l in list2:
        if l in list1:
            list1.remove(l)


def run_analysis(ros_distro, stack_name, workspace, test_depends_on):
    print "Install basic stuff we need"
    print "(Testing on distro %s)"%ros_distro
    print "(Testing stack %s)"%stack_name
    
    # set environment
    print "Set basic environment"
    env = get_environment2()
    env['OS_PLATFORM'] = '%s'%os.environ['OS_PLATFORM']
    env['ROS_DISTRO'] = '%s'%ros_distro
    env['STACK_NAME'] = '%s'%stack_name
    env['WORKSPACE'] = '%s'%workspace
    env['TEST_DEPENDS_ON'] = '%s'%test_depends_on
   
    helper = subprocess.Popen(('bash %s/jenkins_scripts/code_quality/run_analysis.sh'%(os.environ['WORKSPACE'])).split(' '), env=env)
    helper.communicate()
   


def main():
    parser = optparse.OptionParser()
    parser.add_option("--depends_on", action="store_true", default=False)
    (options, args) = parser.parse_args()

    if len(args) <= 1 or len(args)>=3:
        print "Usage: %s ros_distro  stack_name "%sys.argv[0]
    	print " - with ros_distro the name of the ros distribution (e.g. 'electric' or 'fuerte')"
        print " - with stack_name the name of the stack you want to analyze"
        raise BuildException("Wrong arguments for run_analysis script")

    ros_distro = args[0]
    stack_name = args[1]
    workspace = os.environ['WORKSPACE']

    print "Running code_quality_stack on distro %s and stack %s"%(ros_distro, stack_name)
    run_analysis(ros_distro, stack_name, workspace, test_depends_on=options.depends_on)



if __name__ == '__main__':
    # global try
    try:
        main()
        print "run_analysis script finished cleanly"

    # global catch
    except BuildException as ex:
        print ex.msg

    except Exception as ex:
        print "run_analysis script failed. Check out the console output above for details."
        raise ex
