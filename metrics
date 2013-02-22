#!/usr/bin/env python
import sys
import os
sys.path.append('%s/jenkins_scripts/code_quality'%os.environ['WORKSPACE'])
from run_analysis import *
import optparse


def main():
    parser = optparse.OptionParser()
    (options, args) = parser.parse_args()

    if len(args) <= 2 or len(args)%2 != 1:
        print "Usage: %s ros_distro  stack_name "%sys.argv[0]
        print " - with ros_distro the name of the ros distribution (e.g. 'electric' or 'fuerte' or 'groovy')"
        print " - with stack_name the name of the stack you want to analyze"
        print " - build_system 'dry' or 'wet'."
        raise BuildException("Wrong arguments for metrics script")

    ros_distro = args[0]
    stack_name = args[1]
    build_system = args[2]
    workspace = os.environ['WORKSPACE']

    print "Running metrics on distro %s and stack %s"%(ros_distro,stack_name)
    run_analysis(ros_distro, stack_name, workspace, build_system, test_depends_on=True)


if __name__ == '__main__':
    # global try
    try:
        main()
        print "metrics script finished cleanly"

    # global catch
    except BuildException as ex:
        print ex.msg

    except Exception as ex:
        print "metrics script failed. Check out the console output above for details."
        raise ex
