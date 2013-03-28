#!/usr/bin/env python

import rospkg
import rospkg.distro

from job_generation.jobs_common import *
from job_generation.apt_parser import parse_apt
import sys
import os
import optparse 
import subprocess
import traceback
import yaml
import shutil



def main():
    # parse command line options
    #(options, args) = get_options(['rosdistro', 'buildsystem'], ['repeat', 'source-only'])
    parser = optparse.OptionParser()
    (options, args) = parser.parse_args()
    if not options:
       return -1

    platform = args[0]
    arch = args[1]
    email = args[2]
    ros_distro = args[3]
    
    # Parse distro file
    distro_obj = rospkg.distro.load_distro(rospkg.distro.distro_uri(ros_distro))
    print 'Operating on ROS distro %s'%distro_obj.release_name
    env = get_environment()

    try:
        for stack in distro_obj.stacks:
           print 'Analyzing stack %s'%stack
	   h = subprocess.Popen(('run_chroot_jenkins_now %s %s %s metrics %s %s dry'%(platform, arch, email, ros_distro,stack)).split(' '),env=env)
           h.communicate()
    except Exception, ex:
        print "%s. Check the console output for test failure details."%ex
        traceback.print_exc(file=sys.stdout)
        raise ex

if __name__ == '__main__':
    main()
