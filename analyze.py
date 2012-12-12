#!/usr/bin/env python
import string
import fnmatch
import shutil
from common import *
from time import sleep
#
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
#



def remove(list1, list2):
    for l in list2:
        if l in list1:
            list1.remove(l)
#

def analyze(ros_distro, stack_name, workspace, test_depends_on):
    print "Testing on distro %s"%ros_distro
    print "Testing stack %s"%stack_name
    
    # global try
    try:
	
	# Declare variables
    	STACK_DIR = 'stack_overlay'
    	DEPENDS_DIR = 'depends_overlay'
    	DEPENDS_ON_DIR = 'depends_on_overlay'

   	# set environment
    	print "Setting up environment"
    	env = get_environment()
    	env['INSTALL_DIR'] = os.getcwd()
    	env['STACK_BUILD_DIR'] = env['INSTALL_DIR'] + '/build/' + stack_name
    	env['ROS_PACKAGE_PATH'] = '%s:%s:%s:/opt/ros/%s/stacks'%(env['INSTALL_DIR']+'/'+STACK_DIR + '/' + stack_name,
                                                                 env['INSTALL_DIR']+'/'+DEPENDS_DIR,
                                                                 env['INSTALL_DIR']+'/'+DEPENDS_ON_DIR,
                                                                 ros_distro)
    	print "ROS_PACKAGE_PATH = %s"%(env['ROS_PACKAGE_PATH'])
    
    	if 'ros' == stack_name:
        	env['ROS_ROOT'] = env['INSTALL_DIR']+'/'+STACK_DIR+'/ros'
        	print "We're building ROS, so setting the ROS_ROOT to %s"%(env['ROS_ROOT'])
    	else:
        	env['ROS_ROOT'] = '/opt/ros/%s/ros'%ros_distro
        	env['PYTHONPATH'] = env['ROS_ROOT']+'/core/roslib/src'
        	env['PATH'] = '%s:%s:/opt/ros/%s/ros/bin:%s'%(env['QACPPBIN'],env['HTMLVIEWBIN'],ros_distro, os.environ['PATH']) #%s:%s:%s
		#print 'PATH %s'%( env['PATH'])
        	print "Environment set to %s"%str(env)
    
    	#distro = rosdistro.Distro(get_rosdistro_file(ros_distro))

	# Create_new/remove_old STACK_DIR,build,doc,cvs folder
	stack_path = env['INSTALL_DIR']+'/'+STACK_DIR + '/'
	if os.path.exists(stack_path):
	    shutil.rmtree(stack_path)
	os.makedirs(stack_path)

	build_path = env['INSTALL_DIR'] + '/build/'
	if os.path.exists(build_path):
	    shutil.rmtree(build_path)
	os.makedirs(build_path)
	
	doc_path = env['INSTALL_DIR'] + '/doc/'
	if os.path.exists(doc_path):
	    shutil.rmtree(doc_path)
	os.makedirs(doc_path)

	csv_path = env['INSTALL_DIR'] + '/csv/'
	if os.path.exists(csv_path):
	    shutil.rmtree(csv_path)
	os.makedirs(csv_path)
	
        # Parse distro file
        rosdistro_obj = rosdistro.Distro(get_rosdistro_file(ros_distro))
        print 'Operating on ROS distro %s'%rosdistro_obj.release_name
	
        # Install the stacks to test from source
	call('echo -e "\033[33;33m Color Text"', env,
        'Set output-color for installing to yellow')
        print 'Installing the stacks to test from source'
        rosinstall_file = '%s.rosinstall'%STACK_DIR
        if os.path.exists(rosinstall_file):
            os.remove(rosinstall_file)
	if os.path.exists('%s/.rosinstall'%STACK_DIR):
            os.remove('%s/.rosinstall'%STACK_DIR)
        rosinstall = ''
        #for stack in options.stack:
	print 'stack: %s'%(stack_name)
	rosinstall += stack_to_rosinstall(rosdistro_obj.stacks[stack_name], 'devel')
        print 'Generating rosinstall file [%s]'%(rosinstall_file)
        print 'Contents:\n\n'+rosinstall+'\n\n'
        with open(rosinstall_file, 'w') as f:
            f.write(rosinstall)
            print 'rosinstall file [%s] generated'%(rosinstall_file) 
	call('rosinstall --rosdep-yes %s /opt/ros/%s %s'%(STACK_DIR, ros_distro, rosinstall_file), env,
             'Install the stacks to test from source.')
	

        # get all stack dependencies of stacks we're testing
        print "Computing dependencies of stacks we're testing"
        depends_all = []
		
        #for stack in stack_name:    
        stack_xml = '%s/%s/stack.xml'%(STACK_DIR, stack_name)
        call('ls %s'%stack_xml, env, 'Checking if stack %s contains "stack.xml" file'%stack_name)
	 		
        with open(stack_xml) as stack_file:
            depends_one = [str(d) for d in stack_manifest.parse(stack_file.read()).depends]  # convert to list
            print 'Dependencies of stack %s: %s'%(stack_name, str(depends_one))
            for d in depends_one:
                #if not d in stack_name and not d in depends_all:
		if d != stack_name and not d in depends_all:
                    print 'Adding dependencies of stack %s'%d
                    get_depends_all(rosdistro_obj, d, depends_all)
                    print 'Resulting total dependencies of all stacks that get tested: %s'%str(depends_all)
	
        if len(depends_all) > 0:
            # Install Debian packages of stack dependencies
            print 'Installing debian packages of %s dependencies: %s'%(stack_name, str(depends_all))
            call('sudo apt-get update', env)
            call('sudo apt-get install %s --yes'%(stacks_to_debs(depends_all, ros_distro)), env)
	
	else:
            print 'Stack(s) %s do(es) not have any dependencies, not installing anything now'%str(stack_name)
	   
	
	# Install system dependencies of stacks we're testing
        print "Installing system dependencies of stacks we're testing"
        call('rosmake rosdep', env)
        #for stack in stack_name:
        call('rosdep install -y %s'%stack_name, env,
             'Install system dependencies of stack %s'%stack_name)
	
	# Run hudson helper for stacks only
	call('echo -e "\033[33;34m Color Text"', env,
             'Set color from build-output to blue')        
	print "Running Hudson Helper for stacks we're testing"
        res = 0

    	#for r in range(0, int(options.repeat)+1):
	for r in range(0, int(0)+1):
	    env['ROS_TEST_RESULTS_DIR'] = env['ROS_TEST_RESULTS_DIR'] + '/' + STACK_DIR + '_run_' + str(r)
	    helper = subprocess.Popen(('%s/jenkins_scripts/build_helper.py --dir %s build'%(workspace,STACK_DIR + '/' + stack_name)).split(' '), env=env)
            helper.communicate()
            print "helper_return_code is: %s"%(helper.returncode)
	    if helper.returncode != 0:
	        res = helper.returncode
                print "helper_return_code is: %s"%(helper.returncode)
                raise Exception("build_helper.py failed. Often an analysis mistake. Check out the console output above for details.")
	   
            # concatenate filelists
            call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
	    stack_dir = STACK_DIR + '/' + str(stack_name)
            filelist = stack_dir + '/filelist.lst'
            helper = subprocess.Popen(('%s/jenkins_scripts/concatenate_filelists.py --dir %s --filelist %s'%(workspace,stack_dir, filelist)).split(' '), env=env)
            helper.communicate()
            print 'Concatenate filelists done --> %s'%str(stack_name) 
             
            # run cma
            cmaf = stack_dir + '/' + str(stack_name)
            helper = subprocess.Popen(('pal QACPP -cmaf %s -list %s'%(cmaf, filelist)).split(' '), env=env)
            helper.communicate()
            print 'CMA analysis done --> %s'%str(stack_name)  

            # export metrics to yaml and csv files
	    print 'stack_dir: %s '%str(stack_dir)
	    print 'stack_name[0]: %s '%str(stack_name)
            helper = subprocess.Popen(('%s/jenkins_scripts/export_metrics_to_yaml.py --path %s --doc doc --csv csv --config %s/jenkins_scripts/export_config_roscon.yaml'%(workspace,stack_dir,workspace)).split(' '), env=env)
            helper.communicate()
	    call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(stack_name)        
            
            # push results to server
	    print 'stack_dir: %s '%str(stack_dir)
	    print 'stack_name[0]: %s '%str(stack_name)
            helper = subprocess.Popen(('%s/jenkins_scripts/push_results_to_server.py --path %s --doc doc'%(workspace,stack_dir)).split(' '), env=env)
            helper.communicate()
	    call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(stack_name)       
            print 'Analysis of stack %s done'%str(stack_name)
	if res != 0:
            return res


    # global except
    except Exception, ex:
        print "Global exception caught."
        print "%s. Check the console output for test failure details."%ex
        traceback.print_exc(file=sys.stdout)
        raise ex


def main():
    parser = optparse.OptionParser()
    parser.add_option("--depends_on", action="store_true", default=False)
    (options, args) = parser.parse_args()

    if len(args) <= 1 or len(args)>=3:
        print "Usage: %s ros_distro  stack_name "%sys.argv[0]
    	print " - with ros_distro the name of the ros distribution (e.g. 'electric' or 'fuerte')"
        print " - with stack_name the name of the stack you want to analyze"
        raise BuildException("Wrong arguments for analyze script")

    ros_distro = args[0]
    stack_name = args[1]
    workspace = os.environ['WORKSPACE']

    print "Running code_quality_stack on distro %s and stack %s"%(ros_distro, stack_name)
    analyze(ros_distro, stack_name, workspace, test_depends_on=options.depends_on)



if __name__ == '__main__':
    # global try
    try:
        main()
        print "analyze script finished cleanly"

    # global catch
    except BuildException as ex:
        print ex.msg

    except Exception as ex:
        print "analyze script failed. Check out the console output above for details."
        raise ex
