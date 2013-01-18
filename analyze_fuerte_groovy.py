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

def analyze_fuerte_groovy(ros_distro, stack_name, workspace, test_depends_on):
    print "Testing on distro %s"%ros_distro
    print "Testing stack %s"%stack_name
    
    # global try
    try:

        distro_name = ros_distro

        # set environment
        print "Setting up environment"
        env = get_environment()
        env['INSTALL_DIR'] = os.getcwd()
    	env['STACK_BUILD_DIR'] = env['INSTALL_DIR'] + '/build/' + stack_name
        env['ROS_PACKAGE_PATH'] = os.pathsep.join([env['INSTALL_DIR']+'/'+STACK_DIR + '/' + stack_name,
                                                   env['INSTALL_DIR']+'/'+DEPENDS_DIR,
                                                   env['INSTALL_DIR']+'/'+DEPENDS_ON_DIR,
                                                   env['ROS_PACKAGE_PATH']])

        #env['ROS_ROOT'] = '/opt/ros/%s/share/ros'%ros_distro
        #env['PYTHONPATH'] = env['ROS_ROOT']+'/core/roslib/src'
	#env['PATH'] = '%s:%s:%s'%(env['QACPPBIN'],env['HTMLVIEWBIN'], os.environ['PATH'])
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
	stack_list = ['']
	stack_list[0] = stack_name
        rosinstall = stacks_to_rosinstall(stack_list, distro_obj.stacks, 'devel')
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
        #for stack in options.stack:    
        stack_dir = os.path.join(STACK_DIR, stack_name)
        rosstack = rospkg.RosStack(ros_paths=[stack_dir])
        depends_one = rosstack.get_depends(stack_name, implicit=False)
        print 'Dependencies of stack %s: %s'%(stack_name, str(depends_one))
        for d in depends_one:
            #if not d in options.stack and not d in depends_all:
            if d != stack_name and not d in depends_all:
                print 'Adding dependencies of stack %s'%d
                get_depends_all(distro_obj, d, depends_all)
                print 'Resulting total dependencies of all stacks that get tested: %s'%str(depends_all)

        if len(depends_all) > 0:
            #if options.source_only:
                # Install dependencies from source
                #print 'Installing stack dependencies from source'
                #rosinstall = stacks_to_rosinstall(depends_all, distro_obj.released_stacks, 'release-tar')
                #rosinstall_file = '%s.rosinstall'%DEPENDS_DIR
                #print 'Generating rosinstall file [%s]'%(rosinstall_file)
                #print 'Contents:\n\n'+rosinstall+'\n\n'
                #with open(rosinstall_file, 'w') as f:
                 #   f.write(rosinstall)
                  #  print 'rosinstall file [%s] generated'%(rosinstall_file)
                #call('rosinstall -n %s /opt/ros/%s %s'%(DEPENDS_DIR, distro_name, rosinstall_file), env,
                 #    'Install the stack dependencies from source.')
            # Install Debian packages of stack dependencies
            print 'Installing debian packages of "%s" dependencies: %s'%(stack_name, str(depends_all))
            call('sudo apt-get update', env)
            call('sudo apt-get install %s --yes'%(stacks_to_debs(depends_all, distro_name)), env)
        else:
            print 'Stack(s) %s do(es) not have any dependencies, not installing anything now'%str(stack_name)


        # Install system dependencies of stacks re're testing
        print "Installing system dependencies of stacks we're testing"
        #for stack in options.stack:
        call('rosdep install -y %s'%stack_name, env,
             'Install system dependencies of stack %s'%stack_name)


        # Run hudson helper for stacks only
        call('echo -e "\033[33;34m Color Text"', env,
             'Set color from build-output to blue') 
        print "Running Hudson Helper for stacks we're testing"
        res = 0
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
            helper = subprocess.Popen(('%s/jenkins_scripts/export_metrics_to_yaml_fg.py --path %s --doc doc --csv csv --config %s/jenkins_scripts/export_config_roscon.yaml --distro %s --stack %s'%(workspace,stack_dir,workspace, ros_distro, stack_name)).split(' '), env=env)
            helper.communicate()
	    call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(stack_name)        
            
            # push results to server
	    print 'stack_dir: %s '%str(stack_dir)
	    print 'stack_name[0]: %s '%str(stack_name)
            helper = subprocess.Popen(('%s/jenkins_scripts/push_results_to_server_fg.py --path %s --doc doc'%(workspace,stack_dir)).split(' '), env=env)
            helper.communicate()
	    call('echo -e "\033[33;0m Color Text"', env,
             'Set color to white')
            print 'Export metrics to yaml and csv files done --> %s'%str(stack_name)       
            print 'Analysis of stack %s done'%str(stack_name)
	if res != 0:
            return res

        if res != 0:
            return res


    # global except
    except Exception, ex:
        print "Global exception caught. Generating email"
        generate_email("%s. Check the console output for test failure details."%ex, env)
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
        raise BuildException("Wrong arguments for analyze_fuerte_groovy script")

    ros_distro = args[0]
    stack_name = args[1]
    workspace = os.environ['WORKSPACE']

    print "Running code_quality_stack on distro %s and stack %s"%(ros_distro, stack_name)
    analyze_fuerte_groovy(ros_distro, stack_name, workspace, test_depends_on=options.depends_on)



if __name__ == '__main__':
    # global try
    try:
        main()
        print "analyze_fuerte_groovy script finished cleanly"

    # global catch
    except BuildException as ex:
        print ex.msg

    except Exception as ex:
        print "analyze_fuerte_groovy script failed. Check out the console output above for details."
        raise ex


