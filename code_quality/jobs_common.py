#!/usr/bin/python

import roslib
roslib.load_manifest("job_generation")
import os
import optparse
import rosdistro
import hudson
import urllib
import time
import subprocess
import yaml

BOOTSTRAP_SCRIPT = """
cat &gt; $WORKSPACE/script.sh &lt;&lt;DELIM
#!/usr/bin/env bash
set -o errexit
echo "_________________________________BEGIN SCRIPT______________________________________"
sudo apt-get install bzr --yes
sudo apt-get install ros-ROSDISTRO-ros --yes
source /opt/ros/ROSDISTRO/setup.sh

export INSTALL_DIR=/tmp/install_dir
export WORKSPACE=/tmp/ros
export ROS_TEST_RESULTS_DIR=/tmp/ros/test_results
export JOB_NAME=$JOB_NAME
export BUILD_NUMBER=$BUILD_NUMBER
export HUDSON_URL=$HUDSON_URL
export ROS_PACKAGE_PATH=\$INSTALL_DIR/ros_release:\$ROS_PACKAGE_PATH

mkdir -p \$INSTALL_DIR
cd \$INSTALL_DIR

wget  --no-check-certificate http://code.ros.org/svn/ros/installers/trunk/hudson/hudson_helper 
chmod +x  hudson_helper
svn co https://code.ros.org/svn/ros/stacks/ros_release/trunk ros_release
"""

SHUTDOWN_SCRIPT = """
echo "_________________________________END SCRIPT_______________________________________"
DELIM

set -o errexit

rm -rf $WORKSPACE/test_results
rm -rf $WORKSPACE/test_output

wget  --no-check-certificate https://code.ros.org/svn/ros/stacks/ros_release/trunk/hudson/scripts/run_chroot.py -O $WORKSPACE/run_chroot.py
chmod +x $WORKSPACE/run_chroot.py
cd $WORKSPACE &amp;&amp; $WORKSPACE/run_chroot.py --distro=UBUNTUDISTRO --arch=ARCH  --hdd-scratch=/home/rosbuild/install_dir --script=$WORKSPACE/script.sh --ssh-key-file=/home/rosbuild/rosbuild-ssh.tar
"""

BOOTSTRAP_SCRIPT_OSX = """
echo "_________________________________BEGIN SCRIPT______________________________________"
source /Users/rosbuild/ros_bootstrap/setup.bash
export ROS_PACKAGE_PATH=$WORKSPACE/ros_release:$ROS_PACKAGE_PATH

wget  --no-check-certificate http://code.ros.org/svn/ros/installers/trunk/hudson/hudson_helper -O $WORKSPACE/hudson_helper
chmod +x  $WORKSPACE/hudson_helper
svn co https://code.ros.org/svn/ros/stacks/ros_release/trunk $WORKSPACE/ros_release
"""

SHUTDOWN_SCRIPT_OSX = """
echo "_________________________________END SCRIPT_______________________________________"
"""


# the supported Ubuntu distro's for each ros distro
ARCHES = ['amd64', 'i386']

# ubuntu distro mapping to ros distro
UBUNTU_DISTRO_MAP = os_test_platform = {
    'testing': ['lucid', 'maverick'],
    'unstable': ['lucid', 'oneiric'],
    'fuerte': ['lucid', 'oneiric', 'precise'],
    'electric': ['lucid', 'maverick', 'natty', 'oneiric'],
    'diamondback': ['lucid', 'maverick', 'natty'],
    'cturtle': ['lucid', 'maverick', 'karmic'],
}

# Path to hudson server
SERVER = 'http://build.willowgarage.com'
#SERVER = 'http://hudson.willowgarage.com:8080'

# config path
CONFIG_PATH = 'http://wgs24.willowgarage.com/hudson-html/hds.xml'


EMAIL_TRIGGER="""
        <hudson.plugins.emailext.plugins.trigger.WHENTrigger>
          <email>
            <recipientList></recipientList>
            <subject>$PROJECT_DEFAULT_SUBJECT</subject>
            <body>$PROJECT_DEFAULT_CONTENT</body>
            <sendToDevelopers>SEND_DEVEL</sendToDevelopers>
            <sendToRecipientList>true</sendToRecipientList>
            <contentTypeHTML>false</contentTypeHTML>
            <script>true</script>
          </email>
        </hudson.plugins.emailext.plugins.trigger.WHENTrigger>
"""


hudson_scm_managers = {'svn': """
  <scm class="hudson.scm.SubversionSCM">
    <locations>
      <hudson.scm.SubversionSCM_-ModuleLocation>
        <remote>STACKURI</remote>
        <local>STACKNAME</local>
      </hudson.scm.SubversionSCM_-ModuleLocation>
    </locations>
    <useUpdate>false</useUpdate>
    <doRevert>false</doRevert>
    <excludedRegions></excludedRegions>
    <includedRegions></includedRegions>
    <excludedUsers></excludedUsers>
    <excludedRevprop></excludedRevprop>
    <excludedCommitMessages></excludedCommitMessages>
  </scm>
""",
                       'hg': """
  <scm class="hudson.plugins.mercurial.MercurialSCM">
    <source>STACKURI</source>
    <modules></modules>
    <subdir>STACKNAME</subdir>
    <clean>false</clean>
    <forest>false</forest>
    <branch>STACKBRANCH</branch>
  </scm>
""",
                       'bzr': """
  <scm class="hudson.plugins.bazaar.BazaarSCM"> 
    <source>STACKURI STACKNAME</source> 
    <clean>false</clean> 
  </scm> 
""",
                       'git': """

  <scm class="hudson.plugins.git.GitSCM">
    <configVersion>1</configVersion>
    <remoteRepositories>
      <org.spearce.jgit.transport.RemoteConfig>
        <string>origin</string>
        <int>5</int>

        <string>fetch</string>
        <string>+refs/heads/*:refs/remotes/origin/*</string>
        <string>receivepack</string>
        <string>git-upload-pack</string>
        <string>uploadpack</string>
        <string>git-upload-pack</string>

        <string>url</string>
        <string>STACKURI</string>
        <string>tagopt</string>
        <string></string>
      </org.spearce.jgit.transport.RemoteConfig>
    </remoteRepositories>
    <branches>

      <hudson.plugins.git.BranchSpec>
        <name>STACKBRANCH</name>
      </hudson.plugins.git.BranchSpec>
    </branches>
    <localBranch></localBranch>
    <mergeOptions/>
    <recursiveSubmodules>false</recursiveSubmodules>
    <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations>

    <authorOrCommitter>Hudson</authorOrCommitter>
    <clean>false</clean>
    <wipeOutWorkspace>false</wipeOutWorkspace>
    <buildChooser class="hudson.plugins.git.util.DefaultBuildChooser"/>
    <gitTool>Default</gitTool>
    <submoduleCfg class="list"/>
    <relativeTargetDir>STACKNAME</relativeTargetDir>

    <excludedRegions></excludedRegions>
    <excludedUsers></excludedUsers>
  </scm>
"""
}

def stack_to_deb(stack, rosdistro):
    return '-'.join(['ros', rosdistro, str(stack).replace('_','-')])

def stacks_to_debs(stack_list, rosdistro):
    if not stack_list or len(stack_list) == 0:
        return ''
    return ' '.join([stack_to_deb(s, rosdistro) for s in stack_list])


def stack_to_rosinstall(stack_obj, branch):
    try:
        return yaml.dump(rosdistro.stack_to_rosinstall(stack_obj, branch, anonymous=True))
    except rosdistro.DistroException, ex:
        print str(ex)
        return ''


def stacks_to_rosinstall(stack_list,stack_map, branch):
    res = ''
    for s in stack_list:
        if s in stack_map:
            res += stack_to_rosinstall(stack_map[s], branch)
        else:
            print 'Stack "%s" is not in stack list. Not adding this stack to rosinstall file'%s
    return res

    

def get_depends_one(stack):
    name = '%s-%s'%(stack.name, stack.version)
    print 'get_depends_one\nstack.name: %s\nname: %s'%(stack.name, name)
    print 'https://code.ros.org/svn/release/download/stacks/%s/%s/%s.yaml'%(stack.name, name, name)
    for i in range(0, 4):
        try:
            url = urllib.urlopen('https://code.ros.org/svn/release/download/stacks/%s/%s/%s.yaml'%(stack.name, name, name))
            break
        except IOError, e:
            print e[0], e[1]
    conf = url.read()
    if '404 Not Found' in conf:
        print 'Could not get dependencies of stack %s'%stack.name
        return []
    depends = yaml.load(conf)['depends']
    if depends:
        return depends
    else:
        print 'Stack %s does not have any dependencies'%stack.name
        return []

def get_depends_all(distro_obj, stack_name, depends_all):
    start_depth = len(depends_all)
    print start_depth, " depends all ", stack_name
    if not stack_name in depends_all:
        depends_all.append(stack_name)
        try:
            for d in get_depends_one(distro_obj.stacks[stack_name]):
                get_depends_all(distro_obj, d, depends_all)
        except KeyError, ex:
            print "Exception when processing %s.  Key %s is not in distro_obj.stacks: %s"%(stack_name, ex, ", ".join([s for s in distro_obj.stacks]))
            print "depends_all is %s"%(', '.join(depends_all))
            raise ex
    print start_depth, " DEPENDS_ALL ", stack_name, " end depth ", len(depends_all)

def get_environment():
    my_env = os.environ
    my_env['WORKSPACE'] = os.getenv('WORKSPACE', '')
    my_env['INSTALL_DIR'] = os.getenv('INSTALL_DIR', '')
    #my_env['HOME'] = os.getenv('HOME', '')
    my_env['HOME'] = os.path.expanduser('~')
    my_env['JOB_NAME'] = os.getenv('JOB_NAME', '')
    my_env['BUILD_NUMBER'] = os.getenv('BUILD_NUMBER', '')
    my_env['ROS_TEST_RESULTS_DIR'] = os.getenv('ROS_TEST_RESULTS_DIR', my_env['WORKSPACE']+'/test_results')
    my_env['PWD'] = os.getenv('WORKSPACE', '')
    return my_env


def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'os' in ops:
        parser.add_option('--os', dest='os', default='ubuntu', action='store',
                          help='OS name')
    if 'rosdistro' in ops:
        parser.add_option('--rosdistro', dest='rosdistro', default=None, action='store',
                          help='Ros distro name')
    if 'stack' in ops:
        parser.add_option('--stack', dest='stack', default=None, action='append',
                          help='Stack name')
    if 'email' in ops:
        parser.add_option('--email', dest='email', default=None, action='store',
                          help='Email address to send results to')
    if 'arch' in ops:
        parser.add_option('--arch', dest='arch', default=None, action='append',
                          help='Architecture to test')
    if 'ubuntu' in ops:
        parser.add_option('--ubuntu', dest='ubuntu', default=None, action='append',
                          help='Ubuntu distribution to test')
    if 'repeat' in ops:
        parser.add_option('--repeat', dest='repeat', default=0, action='store',
                          help='How many times to repeat the test')
    if 'source-only' in ops:
        parser.add_option('--source-only', dest='source_only', default=False, action='store_true',
                          help="Build everything from source, don't use Debian packages")
    if 'delete' in ops:
        parser.add_option('--delete', dest='delete', default=False, action='store_true',
                          help='Delete jobs from Hudson')    
    if 'wait' in ops:
        parser.add_option('--wait', dest='wait', default=False, action='store_true',
                          help='Wait for running jobs to finish to reconfigure them')    
    if 'rosinstall' in ops:
        parser.add_option('--rosinstall', dest='rosinstall', default=None, action='store',
                          help="Specify the rosinstall file that refers to unreleased code.")
    if 'overlay' in ops:
        parser.add_option('--overlay', dest='overlay', default=None, action='store',
                          help='Create overlay file')
    if 'variant' in ops:
        parser.add_option('--variant', dest='variant', default=None, action='store',
                          help="Specify the variant to create a rosinstall for")
    if 'database' in ops:
        parser.add_option('--database', dest='database', default=None, action='store',
                          help="Specify database file")

    (options, args) = parser.parse_args()
    

    # make repeat an int
    if 'repeat' in ops:
        options.repeat = int(options.repeat)

    # check if required arguments are there
    for r in required:
        if not eval('options.%s'%r):
            print 'You need to specify "--%s"'%r
            return (None, args)

    # postprocessing
    if 'email' in ops and options.email and not '@' in options.email:
        options.email = options.email + '@willowgarage.com'        


    # check if rosdistro exists
    if 'rosdistro' in ops and (not options.rosdistro or not options.rosdistro in UBUNTU_DISTRO_MAP.keys()):
        print 'You provided an invalid "--rosdistro %s" argument. Options are %s'%(options.rosdistro, UBUNTU_DISTRO_MAP.keys())
        return (None, args)

    # check if stacks exist
    if 'stack' in ops and options.stack:
        distro_obj = rosdistro.Distro(get_rosdistro_file(options.rosdistro))
        for s in options.stack:
            if not s in distro_obj.stacks:
                print 'Stack "%s" does not exist in the %s disro file.'%(s, options.rosdistro)
                print 'You need to add this stack to the rosdistro file'
                return (None, args)

    # check if variant exists
    if 'variant' in ops and options.variant:
        distro_obj = rosdistro.Distro(get_rosdistro_file(options.rosdistro))
        if not options.variant in distro_obj.variants:
                print 'Variant "%s" does not exist in the %s disro file.'%(options.variant, options.rosdistro)
                return (None, args)

    return (options, args)


def schedule_jobs(jobs, wait=False, delete=False, start=False, hudson_obj=None):
    # create hudson instance
    if not hudson_obj:
        info = urllib.urlopen(CONFIG_PATH).read().split(',')
        hudson_obj = hudson.Hudson(SERVER, info[0], info[1])

    finished = False
    while not finished:
        jobs_todo = {}
        for job_name in jobs:
            exists = hudson_obj.job_exists(job_name)

            # job is already running
            if exists and hudson_obj.job_is_running(job_name):
                jobs_todo[job_name] = jobs[job_name]
                print "Not reconfiguring running job %s because it is still running"%job_name


            # delete old job
            elif delete:
                if exists:
                    hudson_obj.delete_job(job_name)
                    print " - Deleting job %s"%job_name

            # reconfigure job
            elif exists:
                hudson_obj.reconfig_job(job_name, jobs[job_name])
                if start:
                    hudson_obj.build_job(job_name)
                print " - %s"%job_name

            # create job
            elif not exists:
                hudson_obj.create_job(job_name, jobs[job_name])
                if start:
                    hudson_obj.build_job(job_name)
                print " - %s"%job_name

        if wait and len(jobs_todo) > 0:
            jobs = jobs_todo
            jobs_todo = {}
            time.sleep(10.0)
        else:
            finished = True



def get_rosdistro_file(rosdistro):
    return 'https://code.ros.org/svn/release/trunk/distros/%s.rosdistro'%rosdistro



def get_email_triggers(when, send_devel=True):
    triggers = ''
    for w in when:
        trigger = EMAIL_TRIGGER
        trigger = trigger.replace('WHEN', w)
        if send_devel:
            trigger = trigger.replace('SEND_DEVEL', 'true')
        else:
            trigger = trigger.replace('SEND_DEVEL', 'false')
        triggers += trigger
    return triggers


def get_job_name(jobtype, rosdistro, stack_name, ubuntu, arch):
    if len(stack_name) > 50:
        stack_name = stack_name[0:46]+'_...'
    return "_".join([jobtype, rosdistro, stack_name, ubuntu, arch])


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

def write_file(filename, msg):
    ensure_dir(filename)
    with open(filename, 'w') as f:
        f.write(msg)
    

def generate_email(message, env):
    print message
    write_file(env['WORKSPACE']+'/build_output/buildfailures.txt', message)
    write_file(env['WORKSPACE']+'/test_output/testfailures.txt', '')
    write_file(env['WORKSPACE']+'/build_output/buildfailures-with-context.txt', '')
    


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

        
def get_sys_info():
    arch = 'i386'
    if '64' in call('uname -mrs'):
        arch = 'amd64'
    ubuntudistro = call('lsb_release -a').split('Codename:')[1].strip()
    return (arch, ubuntudistro)
