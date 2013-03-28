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


# Global settings
env= os.environ

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
    if 'snapshot' in ops:
        parser.add_option('--snapshot', dest = 'snapshot', default='snapshot', action='store',
                          help='snapshot folder')
                          
    if 'project' in ops:
        parser.add_option('--project', dest = 'project', default='project', action='store',
                          help='project name')
                          
    if 'stack_name' in ops:
        parser.add_option('--stack_name', dest = 'stack_name', default='stack_name', action='store',
                          help='stack_name')


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
    (options, args) = get_options(['path', 'project', 'stack_name'], ['snapshot'])
    if not options:
        exit(-1)
    
    #load user/passw for qaverify
    lang = None
    qaverify = dict()
    filename = os.path.join(os.environ['HOME'], "chroot_configs", "qaverify.yaml")
    #print 'filename: %s'%filename
    if not os.path.exists(filename):
        raise UtilException('Could not find %s "'%(filename))
    with open(filename, 'r') as f:
        data = yaml.load(f)
    qaverify_user = data['user']
    qaverify_pw = data['password']


    # Upload stacks to QAVerify 
    print 'Upload stack results to QAVerify'    
    print 'project name: %s'%options.project   
    stack_files = [f for f in all_files(options.path) if f.endswith('stack.xml')]
    stack_dirs = [os.path.dirname(f) for f in stack_files]
    for stack_dir in stack_dirs:
        stack = options.stack_name #os.path.basename(stack_dir)
        snapshot_dir = options.snapshot + '/' + stack
	# Phase 1
	call("qaimport QACPP -po qav::code=all -po qav::output=%s/snapshots/%s.qav qav::prqavcs=%s/qaverify-current/client/bin/prqavcs.xml -list %s/filelist.lst "%(options.path, stack, os.environ["HOME"], stack_dir),env, '\nPhase #1: Import to DB format')
	# Phase 2	
	call("upload -prqavcs %s/qaverify-current/client/bin/prqavcs.xml -host localhost -user %s -pass %s -db %s -prod QACPP %s/snapshots/%s.qav"%(os.environ["HOME"], qaverify_user, qaverify_pw, options.project, options.path,stack),env=env, message='\nPhase #2: Upload to Project DB')


	        
    # Upload packages to QAVerify 
    #print 'Upload package results to QAVerify'  
    #package_files = [f for f in all_files(options.path) if f.endswith('manifest.xml')]
    #package_dirs = [os.path.dirname(f) for f in package_files]
    #for package_dir in package_dirs:
    #    package = os.path.basename(package_dir)
    #    print package
    #    doc_dir = options.doc + '/' + package
    # 	 call('sudo scp -oStrictHostKeyChecking=no -r -i %s %s %s'%(WIKI_SERVER_KEY_PATH, doc_dir, ROS_WIKI_SERVER)
    #		,env, 'Push package-yaml-file to ros-wiki ')        

