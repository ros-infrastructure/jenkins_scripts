#!/usr/bin/env python
import os
import sys
sys.path.append('%s/jenkins_scripts/code_quality'%os.environ['WORKSPACE'])
from apt_parser import parse_apt
import optparse 
import subprocess
import traceback
import numpy
import yaml
import codecs
#import roslib; roslib.load_manifest("job_generation")
#from roslib import stack_manifest
#import rosdistro
#from jobs_common import *


# Global settings
#env = get_environment()
#env['INSTALL_DIR'] = os.getcwd()
env= os.environ
#WIKI_SERVER_KEY_PATH = os.environ['HOME'] +'/chroot_configs/keypair.pem'
#ROS_WIKI_SERVER = 'ubuntu@ec2-184-169-231-58.us-west-1.compute.amazonaws.com:~/doc'
ROS_WIKI_SERVER = 'rosbuild@www.ros.org:/var/www/www.ros.org/html/metrics'

def call(command, env=None, message='', ignore_fail=False):
    res = ''
    err = ''
    try:
        print message+'\nExecuting command "%s"'%command
        helper = subprocess.Popen(command.split(' '), stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True, env=env)
        res, err = helper.communicate()
        print str(res)
        print str(err)
        if helper.returncode != 0:
            raise Exception
        return res
    except Exception:
        if not ignore_fail:
            message += "\n=========================================\n"
            message += "Failed to execute '%s'"%command
            message += "\n=========================================\n"
            message += str(res)
            message += "\n=========================================\n"
            message += str(err)
            message += "\n=========================================\n"
            if env:
                message += "ROS_PACKAGE_PATH = %s\n"%env['ROS_PACKAGE_PATH']
                message += "ROS_ROOT = %s\n"%env['ROS_ROOT']
                message += "PYTHONPATH = %s\n"%env['PYTHONPATH']
                message += "\n=========================================\n"
                generate_email(message, env)
            raise Exception

      
def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'path' in ops:
        parser.add_option('--path', dest = 'path', default=None, action='store',
                          help='path to scan')
    if 'path_src' in ops:
        parser.add_option('--path_src', dest = 'path_src', default=None, action='store',
                          help='path_src to source')
    # TODO get rid of doc reference
    if 'doc' in ops:
        parser.add_option('--doc', dest = 'doc', default='metrics', action='store',
                          help='doc folder')

    if 'meta_package' in ops:
        parser.add_option('--meta_package', dest = 'meta_package', default='meta_package', action='store',
                          help='meta_package')

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
    (options, args) = get_options(['path', 'path_src', 'meta_package'], ['doc'])
    if not options:
        exit(-1)
        

    # get packages
    print 'Exporting packages to yaml/csv'  
    package_files = [f for f in all_files(options.path_src) if f.endswith('package.xml')]
    package_dirs = [os.path.dirname(f) for f in package_files]
    for package_dir in package_dirs:
    	if 'Project' in package_dir: continue
        package = os.path.basename(package_dir)
        print package
        doc_dir = options.doc + '/' + package
        new_destination = ROS_WIKI_SERVER + '/groovy'
        call('sudo scp -oStrictHostKeyChecking=no -r %s %s' % (doc_dir, new_destination)
		,env, 'Push package-yaml-file to ros-wiki ')        
