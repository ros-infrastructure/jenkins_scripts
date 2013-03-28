#!/usr/bin/env python

import roslib; roslib.load_manifest("job_generation")
from roslib import stack_manifest
import rosdistro
from jobs_common import *
from apt_parser import parse_apt
import sys
import os
import optparse 
import subprocess
import traceback


def main():
    # parse command line options
    (options, args) = get_options(['rosdistro'], ['repeat', 'source-only'])
    if not options:
       return -1
    
    # Parse distro file
    rosdistro_obj = rosdistro.Distro(get_rosdistro_file(options.rosdistro))
    print 'Operating on ROS distro %s'%rosdistro_obj.release_name
    env = get_environment()

    try:
        for stack in rosdistro_obj.released_stacks:
           print 'Analyzing stack %s'%stack
           #h = subprocess.Popen(('./analyze_stack.py --rosdistro %s --stack %s'%(options.rosdistro,stack)).split(' '), env=env)
	   h = subprocess.Popen(('run_chroot_jenkins_now lucid amd64 kuehnjoh@gmail.com metrics %s %s dry'%(options.rosdistro,stack)).split(' '),env=env)
           h.communicate()
    except Exception, ex:
        print "%s. Check the console output for test failure details."%ex
        traceback.print_exc(file=sys.stdout)
        raise ex

if __name__ == '__main__':
    main()
