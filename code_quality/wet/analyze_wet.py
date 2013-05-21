#!/usr/bin/env python
import os
import sys
sys.path.append('%s/jenkins_scripts'%os.environ['WORKSPACE'])
import subprocess
import string
import fnmatch
import shutil
import rosdep
import optparse
import yaml
from common import *
from time import sleep


def test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on, build_in_workspace=False, sudo=False, no_chroot=False):
    print "Testing on distro %s" % ros_distro
    print "Testing repositories %s" % ', '.join(repo_list)
    print "Testing versions %s" % ', '.join(version_list)
    if test_depends_on:
        print "Testing depends-on"
    else:
        print "Not testing depends on"

    # clean up old tmp directory
    shutil.rmtree(os.path.join(workspace, 'tmp'), ignore_errors=True)

    # set directories
    if build_in_workspace:
        tmpdir = os.path.join(workspace, 'test_repositories')
    else:
        tmpdir = os.path.join('/tmp', 'test_repositories')
    try:
        shutil.rmtree(tmpdir)
    except Exception:
        print "Temp folder did not exist yet"
    repo_sourcespace = os.path.join(tmpdir, 'src_repository')
    dependson_sourcespace = os.path.join(tmpdir, 'src_depends_on')
    repo_buildspace = os.path.join(tmpdir, 'build_repository')
    dependson_buildspace = os.path.join(tmpdir, 'build_depend_on')

    if no_chroot:
        print "Skip adding ros sources to apt"
    else:
        # Add ros sources to apt
        print "Add ros sources to apt"
        ros_apt = '/etc/apt/sources.list.d/ros-latest.list'
        if not os.path.exists(ros_apt):
            with open(ros_apt, 'w') as f:
                f.write("deb http://packages.ros.org/ros-shadow-fixed/ubuntu %s main" % os.environ['OS_PLATFORM'])
            call("wget http://packages.ros.org/ros.key -O %s/ros.key" % workspace)
            call("apt-key add %s/ros.key" % workspace)
        apt_get_update(sudo)


    if no_chroot:
        print "Skip installing packages which are necessary to run this script"
    else:
        # install stuff we need
        print "Installing Debian packages we need for running this script"
        apt_get_install(['python-catkin-pkg', 'python-rosinstall', 'python-rosdistro'], sudo=sudo)


    print "ros_distro value is ", ros_distro
    if ros_distro != 'fuerte':
        return _test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on,
                       repo_sourcespace, dependson_sourcespace, repo_buildspace, dependson_buildspace,
                       sudo, no_chroot)
    else:
        return _test_repositories_fuerte(ros_distro, repo_list, version_list, workspace, test_depends_on,
                       repo_sourcespace, dependson_sourcespace, repo_buildspace, dependson_buildspace,
                       sudo, no_chroot)




def _test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on,
                       repo_sourcespace, dependson_sourcespace, repo_buildspace, dependson_buildspace,
                       sudo=False, no_chroot=False):
    from catkin_pkg.package import InvalidPackage, parse_package_string
    from rosdistro import get_cached_release, get_index, get_index_url, get_source_file
    from rosdistro.dependency_walker import DependencyWalker
    from rosdistro.manifest_provider import get_release_tag

    index = get_index(get_index_url())
    print "Parsing rosdistro file for %s" % ros_distro
    release = get_cached_release(index, ros_distro)
    print "Parsing devel file for %s" % ros_distro
    source_file = get_source_file(index, ros_distro)

    # Create rosdep object
    print "Create rosdep object"
    rosdep_resolver = rosdep.RosDepResolver(ros_distro, sudo, no_chroot)

    # download the repo_list from source
    print "Creating rosinstall file for repo list"
    rosinstall = ""
    for repo_name, version in zip(repo_list, version_list):
        if version == 'devel':
            if repo_name not in source_file.repositories:
                raise BuildException("Repository %s does not exist in Devel Distro" % repo_name)
            print "Using devel distro file to download repositories"
            rosinstall += _generate_rosinstall_for_repo(source_file.repositories[repo_name])
        else:
            if repo_name not in release.repositories:
                raise BuildException("Repository %s does not exist in Ros Distro" % repo_name)
            repo = release.repositories[repo_name]
            if version not in ['latest', 'master']:
                assert repo.version is not None, 'Repository "%s" does not have a version set' % repo_name
            assert 'release' in repo.tags, 'Repository "%s" does not have a "release" tag set' % repo_name
            for pkg_name in repo.package_names:
                release_tag = get_release_tag(repo, pkg_name)
                if version in ['latest', 'master']:
                    release_tag = '/'.join(release_tag.split('/')[:-1])
                print 'Using tag "%s" of release distro file to download package "%s from repo "%s' % (version, pkg_name, repo_name)
                rosinstall += _generate_rosinstall_for_repo(release.repositories[repo_name], version=release_tag)
    print "rosinstall file for all repositories: \n %s" % rosinstall
    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        f.write(rosinstall)
    print "Install repo list from source"
    os.makedirs(repo_sourcespace)
    call("rosinstall %s %s/repo.rosinstall --catkin" % (repo_sourcespace, workspace))

    # get the repositories build dependencies
    print "Get build dependencies of repo list"
    repo_build_dependencies = get_dependencies(repo_sourcespace, build_depends=True, test_depends=False)
    # ensure that catkin gets installed, for non-catkin packages so that catkin_make_isolated is available
    if 'catkin' not in repo_build_dependencies:
        repo_build_dependencies.append('catkin')
    print "Install build dependencies of repo list: %s" % (', '.join(repo_build_dependencies))
    apt_get_install(repo_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file for repositories that use catkin
    print "Removing the CMakeLists.txt file generated by rosinstall"
    os.remove(os.path.join(repo_sourcespace, 'CMakeLists.txt'))
    print "Create a new CMakeLists.txt file using catkin"

    # get environment
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)

    # check if source workspace contains only package built with catkin
    non_catkin_pkgs = _get_non_catkin_packages(repo_sourcespace)

    # make build folder and change into it
    os.makedirs(repo_buildspace)
    os.chdir(repo_buildspace)

    # make test results dir
    test_results_dir = os.path.join(workspace, 'test_results')
    if os.path.exists(test_results_dir):
        shutil.rmtree(test_results_dir)
    os.makedirs(test_results_dir)

    if not non_catkin_pkgs:
        print "Build catkin workspace"
        call("catkin_init_workspace %s" % repo_sourcespace, ros_env)
        repos_test_results_dir = os.path.join(test_results_dir, 'repos')
        helper = subprocess.Popen(('cmake %s -DCMAKE_TOOLCHAIN_FILE=/opt/ros/groovy/share/ros/core/rosbuild/rostoolchain.cmake -DCATKIN_TEST_RESULTS_DIR=%s'%(repo_sourcespace,repos_test_results_dir)).split(' '), env=ros_env)
        helper.communicate()
        res = 0
        if helper.returncode != 0:
            res = helper.returncode
        ros_env_repo = get_ros_env(os.path.join(repo_buildspace, 'devel/setup.bash'))
    
        # build repositories
        print "Build repo list"
        print "CMAKE_PREFIX_PATH: %s"%ros_env['CMAKE_PREFIX_PATH']
        call("make", ros_env)
        
        # Concatenate filelists
        print '-----------------  Concatenate filelists -----------------  '
        filelist = '%s'%repo_buildspace + '/filelist.lst'
        helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/concatenate_filelists.py --dir %s --filelist %s'%(workspace,repo_buildspace, filelist)).split(' '), env=os.environ)
        helper.communicate()
        print '////////////////// cma analysis done ////////////////// \n\n'

        # Run CMA
        print '-----------------  Run CMA analysis -----------------  '
        cmaf = repo_sourcespace#repo_buildspace
        helper = subprocess.Popen(('pal QACPP -cmaf %s -list %s'%(cmaf, filelist)).split(' '), env=os.environ)
        helper.communicate()
        print '////////////////// cma analysis done ////////////////// \n\n'

        # Export metrics to yaml and csv files
        # get uri infos
        #uri= distro.get_repositories()[repo_list[0]].url
        repo = source_file.get_data()['repositories']
        repo_data = repo.get_data()
        uri = repo_data['url']
        uri_info= repo_data['version']
        vcs_type= repo_data['type']
    
        print '-----------------  Export metrics to yaml and csv files ----------------- '
        helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/export_metrics_to_yaml_wet.py --path %s --path_src %s --doc metrics --csv csv --config %s/jenkins_scripts/code_quality/export_config.yaml --distro %s --stack %s --uri %s --uri_info %s --vcs_type %s'%(workspace, repo_buildspace, repo_sourcespace, workspace, ros_distro, repo_list, uri,  uri_info, vcs_type)).split(' '), env=os.environ)
        helper.communicate()
        print '////////////////// export metrics to yaml and csv files done ////////////////// \n\n'     
 
        # Push results to server
        print '-----------------  Push results to server -----------------  '
        helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/push_results_to_server_wet.py --path %s --doc metrics --path_src %s --meta_package %s'%(workspace, repo_buildspace, repo_sourcespace, repo_list)).split(' '), env=os.environ)
        helper.communicate()
        print '////////////////// push results to server done ////////////////// \n\n' 


        # Upload results to QAVerify
        print ' -----------------  upload results to QAVerify -----------------  '
        shutil.rmtree(os.path.join(workspace, 'snapshots_path'), ignore_errors=True)
        os.makedirs(os.path.join(workspace, 'snapshots_path'))
        snapshots_path = '%s/snapshots_path'%workspace
        project_name = repo_list[0] + '-' + ros_distro
        helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/upload_to_QAVerify_wet.py --path %s --snapshot %s --project %s --stack_name %s'%(workspace, repo_buildspace, snapshots_path, project_name,  repo_list[0])).split(' '), env=os.environ)
        helper.communicate()
        print '////////////////// upload results to QAVerify done ////////////////// \n\n'
        if os.path.exists(snapshots_path):
            shutil.rmtree(snapshots_path)

    else:
        print "Build workspace with non-catkin packages in isolation"
        # work around catkin_make_isolated issue (at least with version 0.5.65 of catkin)
        os.makedirs(os.path.join(repo_buildspace, 'devel_isolated'))
        call('catkin_make_isolated --source %s --install-space install_isolated --install' % repo_sourcespace, ros_env)
        setup_file = os.path.join(repo_buildspace, 'install_isolated', 'setup.sh')
        ros_env = get_ros_env(setup_file)

    if res != 0:
        print "helper_return_code is: %s"%(helper.returncode)
        assert 'analysis_wet.py failed'
        raise Exception("analysis_wet.py failed. Check out the console output above for details.")
    
    # create dummy test results
    env = dict()
    env['INSTALL_DIR'] = os.getenv('INSTALL_DIR', '')
    test_results_path = workspace + '/test_results'
    if os.path.exists(test_results_path):
        shutil.rmtree(test_results_path)
    os.makedirs(test_results_path)
    test_file= test_results_path + '/test_file.xml' 
    f = open(test_file, 'w')
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<testsuite tests="1" failures="0" time="1" errors="0" name="dummy test">\n')
    f.write('  <testcase name="dummy rapport" classname="Results" /> \n')
    f.write('</testsuite> \n')
    f.close()


def _get_non_catkin_packages(basepath):
    from catkin_pkg.packages import find_packages
    pkgs = []
    packages = find_packages(basepath)
    for pkg in packages.values():
        if _is_non_catkin_package(pkg):
            pkgs.append(pkg.name)
    return pkgs


def _is_non_catkin_package(pkg):
    if 'build_type' in [e.tagname for e in pkg.exports]:
        build_type = [e.content for e in pkg.exports if e.tagname == 'build_type'][0]
        if build_type != 'catkin':
            return True
    return False


def _test_repositories_fuerte(ros_distro, repo_list, version_list, workspace, test_depends_on,
                              repo_sourcespace, dependson_sourcespace, repo_buildspace, dependson_buildspace,
                              sudo=False, no_chroot=False):
    import rosdistro

    # parse the rosdistro file
    print "Parsing rosdistro file for %s" % ros_distro
    distro = rosdistro.RosDistro(ros_distro)
    print "Parsing devel file for %s" % ros_distro
    devel = rosdistro.DevelDistro(ros_distro)

    # Create rosdep object
    print "Create rosdep object"
    rosdep_resolver = rosdep.RosDepResolver(ros_distro, sudo, no_chroot)

    # download the repo_list from source
    print "Creating rosinstall file for repo list"
    rosinstall = ""
    for repo, version in zip(repo_list, version_list):
        if version == 'devel':
            if repo not in devel.repositories:
                raise BuildException("Repository %s does not exist in Devel Distro" % repo)
            print "Using devel distro file to download repositories"
            rosinstall += devel.repositories[repo].get_rosinstall()
        else:
            if repo not in distro.get_repositories():
                raise BuildException("Repository %s does not exist in Ros Distro" % repo)
            if version in ['latest', 'master']:
                print "Using latest release distro file to download repositories"
                rosinstall += distro.get_rosinstall(repo, version='master')
            else:
                print "Using version %s of release distro file to download repositories" % version
                rosinstall += distro.get_rosinstall(repo, version)
    print "rosinstall file for all repositories: \n %s" % rosinstall
    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        f.write(rosinstall)
    print "Install repo list from source"
    os.makedirs(repo_sourcespace)
    call("rosinstall %s %s/repo.rosinstall --catkin" % (repo_sourcespace, workspace))

    # get the repositories build dependencies
    print "Get build dependencies of repo list"
    repo_build_dependencies = get_dependencies(repo_sourcespace, build_depends=True, test_depends=False)
    print "Install build dependencies of repo list: %s" % (', '.join(repo_build_dependencies))
    apt_get_install(repo_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file for repositories that use catkin
    print "Removing the CMakeLists.txt file generated by rosinstall"
    os.remove(os.path.join(repo_sourcespace, 'CMakeLists.txt'))
    print "Create a new CMakeLists.txt file using catkin"
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)
    call("catkin_init_workspace %s" % repo_sourcespace, ros_env)
    test_results_dir = os.path.join(workspace, 'test_results')
    repos_test_results_dir = os.path.join(test_results_dir, 'repos')
    os.makedirs(repo_buildspace)
    os.chdir(repo_buildspace)
    helper = subprocess.Popen(('cmake %s -DCMAKE_TOOLCHAIN_FILE=/opt/ros/groovy/share/ros/core/rosbuild/rostoolchain.cmake -DCATKIN_TEST_RESULTS_DIR=%s'%(repo_sourcespace,repos_test_results_dir)).split(' '), env=ros_env)
    helper.communicate()
    res = 0
    if helper.returncode != 0:
        res = helper.returncode
    ros_env_repo = get_ros_env(os.path.join(repo_buildspace, 'devel/setup.bash'))
    
    # build repositories
    print "Build repo list"
    print "CMAKE_PREFIX_PATH: %s"%ros_env['CMAKE_PREFIX_PATH']
    call("make", ros_env)
        
    # Concatenate filelists
    print '-----------------  Concatenate filelists -----------------  '
    filelist = '%s'%repo_buildspace + '/filelist.lst'
    helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/concatenate_filelists.py --dir %s --filelist %s'%(workspace,repo_buildspace, filelist)).split(' '), env=os.environ)
    helper.communicate()
    print '////////////////// cma analysis done ////////////////// \n\n'

    # Run CMA
    print '-----------------  Run CMA analysis -----------------  '
    cmaf = repo_sourcespace#repo_buildspace
    helper = subprocess.Popen(('pal QACPP -cmaf %s -list %s'%(cmaf, filelist)).split(' '), env=os.environ)
    helper.communicate()
    print '////////////////// cma analysis done ////////////////// \n\n'

    # Export metrics to yaml and csv files
    # get uri infos
    uri= distro.get_repositories()[repo_list[0]].url
    uri_info= 'master' 
    vcs_type= 'git'
    
    print '-----------------  Export metrics to yaml and csv files ----------------- '
    helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/export_metrics_to_yaml_wet.py --path %s --path_src %s --doc metrics --csv csv --config %s/jenkins_scripts/code_quality/export_config.yaml --distro %s --stack %s --uri %s --uri_info %s --vcs_type %s'%(workspace, repo_buildspace, repo_sourcespace, workspace, ros_distro, repo_list, uri,  uri_info, vcs_type)).split(' '), env=os.environ)
    helper.communicate()
    print '////////////////// export metrics to yaml and csv files done ////////////////// \n\n'     
 
    # Push results to server
    print '-----------------  Push results to server -----------------  '
    helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/push_results_to_server_wet.py --path %s --doc metrics --path_src %s --meta_package %s'%(workspace, repo_buildspace, repo_sourcespace, repo_list)).split(' '), env=os.environ)
    helper.communicate()
    print '////////////////// push results to server done ////////////////// \n\n' 


    # Upload results to QAVerify
    print ' -----------------  upload results to QAVerify -----------------  '
    shutil.rmtree(os.path.join(workspace, 'snapshots_path'), ignore_errors=True)
    os.makedirs(os.path.join(workspace, 'snapshots_path'))
    snapshots_path = '%s/snapshots_path'%workspace
    project_name = repo_list[0] + '-' + ros_distro
    helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/wet/upload_to_QAVerify_wet.py --path %s --snapshot %s --project %s --stack_name %s'%(workspace, repo_buildspace, snapshots_path, project_name,  repo_list[0])).split(' '), env=os.environ)
    helper.communicate()
    print '////////////////// upload results to QAVerify done ////////////////// \n\n'
    if os.path.exists(snapshots_path):
        shutil.rmtree(snapshots_path)


    if res != 0:
        print "helper_return_code is: %s"%(helper.returncode)
        assert 'analysis_wet.py failed'
        raise Exception("analysis_wet.py failed. Check out the console output above for details.")
    
    # create dummy test results
    env = dict()
    env['INSTALL_DIR'] = os.getenv('INSTALL_DIR', '')
    test_results_path = workspace + '/test_results'
    if os.path.exists(test_results_path):
        shutil.rmtree(test_results_path)
    os.makedirs(test_results_path)
    test_file= test_results_path + '/test_file.xml' 
    f = open(test_file, 'w')
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<testsuite tests="1" failures="0" time="1" errors="0" name="dummy test">\n')
    f.write('  <testcase name="dummy rapport" classname="Results" /> \n')
    f.write('</testsuite> \n')
    f.close()


def _generate_rosinstall_for_pkg(repo, pkg_name):
    from rosdistro.manifest_provider import get_release_tag
    repo_data = {
        'local-name': pkg_name,
        'uri': repo.url,
        'version': get_release_tag(repo, pkg_name)
    }
    return yaml.safe_dump([{repo.type: repo_data}], default_style=False)


def _generate_rosinstall_for_repo(repo, version=None):
    repo_data = {
        'local-name': repo.name,
        'uri': repo.url
    }
    if version is not None:
        repo_data['version'] = version
    elif repo.version:
        repo_data['version'] = repo.version
    return yaml.safe_dump([{repo.type: repo_data}], default_style=False)



def main():
    parser = optparse.OptionParser()
    parser.add_option("--depends_on", action="store_true", default=False)
    (options, args) = parser.parse_args()

    if len(args) <= 2 or len(args)%2 != 1:
        print "Usage: %s ros_distro repo1 version1 repo2 version2 ..."%sys.argv[0]
        print " - with ros_distro the name of the ros distribution (e.g. 'fuerte' or 'groovy')"
        print " - with repo the name of the repository"
        print " - with version 'latest', 'devel', or the actual version number (e.g. 0.2.5)."
        raise BuildException("Wrong arguments for analyze_wet script")

    ros_distro = args[0]

    repo_list = [args[i] for i in range(1, len(args), 2)]
    version_list = [args[i+1] for i in range(1, len(args), 2)]
    workspace = os.environ['WORKSPACE']

    print "Running analyze_wet test on distro %s and repositories %s"%(ros_distro,
                                                                      ', '.join(["%s (%s)"%(r,v) for r, v in zip(repo_list, version_list)]))
    test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on=options.depends_on)



if __name__ == '__main__':
    # global try
    try:
        main()
        print "analyze_wet script finished cleanly"

    # global catch
    except BuildException as ex:
        print ex.msg

    except Exception as ex:
        print "analyze_wet script failed. Check out the console output above for details."
        raise ex
