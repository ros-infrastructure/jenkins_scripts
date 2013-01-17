#!/usr/bin/python

STACK_DIR = 'stack_overlay'
DEPENDS_DIR = 'depends_overlay'
DEPENDS_ON_DIR = 'depends_on_overlay'

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

def remove(list1, list2):
    for l in list2:
        if l in list1:
            list1.remove(l)

def main():
    # global try
    try:

        # parse command line options
        (options, args) = get_options(['stack', 'rosdistro'], ['repeat', 'source-only'])
        if not options:
            return -1
        distro_name = options.rosdistro

        # set environment
        print "Setting up environment"
        env = get_environment()
      env['INSTALL_DIR'] = os.getcwd()
    	env['STACK_BUILD_DIR'] = env['INSTALL_DIR'] + '/build/' + options.stack[0]
        env['ROS_PACKAGE_PATH'] = os.pathsep.join([env['INSTALL_DIR']+'/'+STACK_DIR,
                                                   env['INSTALL_DIR']+'/'+DEPENDS_DIR,
                                                   env['INSTALL_DIR']+'/'+DEPENDS_ON_DIR,
                                                   env['ROS_PACKAGE_PATH']])
        print "Environment set to %s"%str(env)


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
        distro_obj = rospkg.distro.load_distro(rospkg.distro.distro_uri(distro_name))
        print 'Operating on ROS distro %s'%distro_obj.release_name


        # Install the stacks to test from source
        call('echo -e "\033[33;33m Color Text"', env,
        'Set output-color for installing to yellow')
        print 'Installing the stacks to test from source'
        rosinstall = stacks_to_rosinstall(options.stack, distro_obj.stacks, 'devel')
        rosinstall_file = '%s.rosinstall'%STACK_DIR
        print 'Generating rosinstall file [%s]'%(rosinstall_file)
        print 'Contents:\n\n'+rosinstall+'\n\n'
        with open(rosinstall_file, 'w') as f:
            f.write(rosinstall)
            print 'rosinstall file [%s] generated'%(rosinstall_file)
        call('rosinstall -n %s /opt/ros/%s %s'%(STACK_DIR, distro_name, rosinstall_file), env,
             'Install the stacks to test from source.')

        # get all stack dependencies of stacks we're testing
        print "Computing dependencies of stacks we're testing"
        depends_all = []
        for stack in options.stack:    
            stack_dir = os.path.join(STACK_DIR, stack)
            rosstack = rospkg.RosStack(ros_paths=[stack_dir])
            depends_one = rosstack.get_depends(stack, implicit=False)
            print 'Dependencies of stack %s: %s'%(stack, str(depends_one))
            for d in depends_one:
                if not d in options.stack and not d in depends_all:
                    print 'Adding dependencies of stack %s'%d
                    get_depends_all(distro_obj, d, depends_all)
                    print 'Resulting total dependencies of all stacks that get tested: %s'%str(depends_all)

        if len(depends_all) > 0:
            if options.source_only:
                # Install dependencies from source
                print 'Installing stack dependencies from source'
                rosinstall = stacks_to_rosinstall(depends_all, distro_obj.released_stacks, 'release-tar')
                rosinstall_file = '%s.rosinstall'%DEPENDS_DIR
                print 'Generating rosinstall file [%s]'%(rosinstall_file)
                print 'Contents:\n\n'+rosinstall+'\n\n'
                with open(rosinstall_file, 'w') as f:
                    f.write(rosinstall)
                    print 'rosinstall file [%s] generated'%(rosinstall_file)
                call('rosinstall -n %s /opt/ros/%s %s'%(DEPENDS_DIR, distro_name, rosinstall_file), env,
                     'Install the stack dependencies from source.')
            else:
                # Install Debian packages of stack dependencies
                print 'Installing debian packages of "%s" dependencies: %s'%(stack, str(depends_all))
                call('sudo apt-get update', env)
                call('sudo apt-get install %s --yes'%(stacks_to_debs(depends_all, distro_name)), env)
        else:
            print 'Stack(s) %s do(es) not have any dependencies, not installing anything now'%str(options.stack)


        # Install system dependencies of stacks re're testing
        print "Installing system dependencies of stacks we're testing"
        for stack in options.stack:
            call('rosdep install -y %s'%stack, env,
                 'Install system dependencies of stack %s'%stack)


        # Run hudson helper for stacks only
        call('echo -e "\033[33;34m Color Text"', env,
             'Set color from build-output to blue') 
        print "Running Hudson Helper for stacks we're testing"
        res = 0
        for r in range(0, int(options.repeat)+1):
            env['ROS_TEST_RESULTS_DIR'] = env['ROS_TEST_RESULTS_DIR'] + '/' + STACK_DIR + '_run_' + str(r)
            helper = subprocess.Popen(('./hudson_helper --dir-test %s build'%(STACK_DIR + '/' + options.stack[0] )).split(' '), env=env)
            helper.communicate()
            print "helper_return_code is: %s"%(helper.returncode)
            if helper.returncode != 0:
                res = helper.returncode
                print "helper_return_code is: %s"%(helper.returncode)
                raise Exception("build_helper.py failed. Often an analysis mistake. Check out the console output above for details.")
        
            # concatenate filelists
            call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            stack_dir = STACK_DIR + '/' + options.stack[0]
            filelist = stack_dir + '/filelist.lst'
            helper = subprocess.Popen(('./concatenate_filelists.py --dir %s --filelist %s'%(stack_dir, filelist)).split(' '), env=env)
            helper.communicate()
            print 'Concatenate filelists done --> %s'%str(options.stack) 
             
            # run cma
            cmaf = stack_dir + '/' + options.stack[0]
            helper = subprocess.Popen(('pal QACPP -cmaf %s -list %s'%(cmaf, filelist)).split(' '), env=env)
            helper.communicate()
            print 'CMA analysis done --> %s'%str(options.stack)  

            # export metrics to yaml and csv files
            print 'stack_dir: %s '%str(stack_dir)
            print 'options.stack[0]: %s '%str(options.stack[0])
            helper = subprocess.Popen(('./export_metrics_to_yaml.py --path %s --doc doc --csv csv --config export_config_roscon.yaml --distro %s --stack %s'%((stack_dir, distro_name, options.stack[0]))).split(' '), env=env)
            helper.communicate()
            call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(options.stack)             
            print 'Analysis of stack %s done'%str(options.stack)

            # push results to server
	    print 'stack_dir: %s '%str(stack_dir)
	    print 'stack_name[0]: %s '%str(options.stack[0])
            helper = subprocess.Popen(('./push_results_to_server.py --path %s --doc doc'%(stack_dir)).split(' '), env=env)
            helper.communicate()
	    call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(stack_name)       
            print 'Analysis of stack %s done'%str(stack_name)

        if res != 0:
            return res


    # global except
    except Exception, ex:
        print "Global exception caught. Generating email"
        generate_email("%s. Check the console output for test failure details."%ex, env)
        traceback.print_exc(file=sys.stdout)
        raise ex


if __name__ == '__main__':
    try:
        res = main()
        sys.exit( res )
    except Exception, ex:
        sys.exit(-1)





