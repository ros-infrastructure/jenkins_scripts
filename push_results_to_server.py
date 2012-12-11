#!/usr/bin/env python
import os
from apt_parser import parse_apt
import sys
import optparse 
import subprocess
import traceback
import numpy
import yaml
import codecs
import roslib; roslib.load_manifest("job_generation")
from roslib import stack_manifest
import rosdistro
from jobs_common import *


# Global settings
env = get_environment()
env['INSTALL_DIR'] = os.getcwd()
WIKI_SERVER_KEY_PATH = os.environ['HOME'] +'/chroot_configs/ec2-keypair.pem'
ROS_WIKI_SERVER = 'ubuntu@ec2-184-169-231-58.us-west-1.compute.amazonaws.com:~/doc'
      
def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'path' in ops:
        parser.add_option('--path', dest = 'path', default=None, action='store',
                          help='path to scan')
    if 'doc' in ops:
        parser.add_option('--doc', dest = 'doc', default='doc', action='store',
                          help='doc folder')

    (options, args) = parser.parse_args()

    # check if required arguments are there
    for r in required:
        if not eval('options.%s'%r):
            print 'You need to specify "--%s"'%r
            return (None, args)

    return (options, args)
    

def all_files(directory):
    for path, dirs, files in os.walk(directory):
        for f in files:
            yield os.path.abspath(os.path.join(path, f))
            

if __name__ == '__main__':   
    (options, args) = get_options(['path'], ['doc'])
    if not options:
        exit(-1)
    

    # get stacks  
    print 'Exporting stacks to yaml/csv'      
    stack_files = [f for f in all_files(options.path) if f.endswith('stack.xml')]
    stack_dirs = [os.path.dirname(f) for f in stack_files]
    for stack_dir in stack_dirs:
        print stack_dir
        stack = os.path.basename(stack_dir)
        doc_dir = options.doc + '/' + stack
	call('sudo scp -oStrictHostKeyChecking=no -r -i %s %s %s'%(WIKI_SERVER_KEY_PATH, doc_dir, ROS_WIKI_SERVER)
		,env, 'Push stack-yaml-file to ros-wiki ')
	        
    # get packages
    print 'Exporting packages to yaml/csv'  
    package_files = [f for f in all_files(options.path) if f.endswith('manifest.xml')]
    package_dirs = [os.path.dirname(f) for f in package_files]
    for package_dir in package_dirs:
        package = os.path.basename(package_dir)
        print package
        doc_dir = options.doc + '/' + package
   	call('sudo scp -oStrictHostKeyChecking=no -r -i %s %s %s'%(WIKI_SERVER_KEY_PATH, doc_dir, ROS_WIKI_SERVER)
		,env, 'Push package-yaml-file to ros-wiki ')        

