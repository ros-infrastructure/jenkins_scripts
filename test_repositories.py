#!/usr/bin/env python

from __future__ import print_function

import optparse
import os
import re
import rosdep
import shutil
import sys

from common import append_pymodules_if_needed, apt_get_install, apt_get_update, BuildException, call, create_test_result, ensure_test_results, get_dependencies, get_ros_env


def test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on, build_in_workspace=False, sudo=False, no_chroot=False):
    print("Testing on distro %s" % ros_distro)
    print("Testing repositories %s" % ', '.join(repo_list))
    print("Testing versions %s" % ', '.join(version_list))
    if test_depends_on:
        print("Testing depends-on")
    else:
        print("Not testing depends on")

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
        print("Temp folder did not exist yet")
    repo_sourcespace = os.path.join(tmpdir, 'src_repository')
    dependson_sourcespace = os.path.join(tmpdir, 'src_depends_on')
    repo_buildspace = os.path.join(tmpdir, 'build_repository')
    dependson_buildspace = os.path.join(tmpdir, 'build_depend_on')

    if no_chroot:
        print("Skip adding ros sources to apt")
    else:
        call("apt-get update")
        call("apt-get install ca-certificates --yes")
        call("apt-get install curl --yes")

        # Add ros sources to apt
        print("Add ros sources to apt")
        ros_apt = '/etc/apt/sources.list.d/ros-latest.list'
        if not os.path.exists(ros_apt):
            with open(ros_apt, 'w') as f:
                f.write("deb http://repos.ros.org/repos/ros-shadow-fixed/ubuntu %s main" % os.environ['OS_PLATFORM'])
            call("curl http://packages.ros.org/ros.key -o %s/ros.key" % workspace)
            call("apt-key add %s/ros.key" % workspace)
        apt_get_update(sudo)

    if no_chroot:
        print("Skip installing packages which are necessary to run this script")
    else:
        # install stuff we need
        print("Installing Debian packages we need for running this script")
        apt_get_install(['python-catkin-pkg', 'python-rosinstall', 'python-rosdistro', 'python-yaml'], sudo=sudo)

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
    append_pymodules_if_needed()
    from catkin_pkg.package import InvalidPackage, parse_package_string
    from rosdistro import get_cached_release, get_index, get_index_url, get_source_file
    from rosdistro.dependency_walker import DependencyWalker
    from rosdistro.manifest_provider import get_release_tag

    index = get_index(get_index_url())
    print("Parsing rosdistro file for %s" % ros_distro)
    release = get_cached_release(index, ros_distro)
    print("Parsing devel file for %s" % ros_distro)
    source_file = get_source_file(index, ros_distro)

    # Create rosdep object
    print("Create rosdep object")
    rosdep_resolver = rosdep.RosDepResolver(ros_distro, sudo, no_chroot)

    # download the repo_list from source
    print("Creating rosinstall file for repo list")
    rosinstall = ""
    for repo_name, version in zip(repo_list, version_list):
        if version == 'devel':
            if repo_name not in source_file.repositories:
                raise BuildException("Repository %s does not exist in Devel Distro" % repo_name)
            print("Using devel distro file to download repositories")
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
                print('Using tag "%s" of release distro file to download package "%s from repo "%s' % (version, pkg_name, repo_name))
                rosinstall += _generate_rosinstall_for_pkg_version(release.repositories[repo_name], pkg_name, release_tag)
    print("rosinstall file for all repositories: \n %s" % rosinstall)
    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        f.write(rosinstall)
    print("Install repo list from source")
    os.makedirs(repo_sourcespace)
    call("rosinstall %s %s/repo.rosinstall --catkin" % (repo_sourcespace, workspace))

    extract_notification_recipients(repo_sourcespace)

    # get the repositories build dependencies
    print("Get build dependencies of repo list")
    repo_build_dependencies = get_dependencies(repo_sourcespace, build_depends=True, test_depends=False)
    # ensure that catkin gets installed, for non-catkin packages so that catkin_make_isolated is available
    if 'catkin' not in repo_build_dependencies:
        repo_build_dependencies.append('catkin')
    print("Install build dependencies of repo list: %s" % (', '.join(repo_build_dependencies)))
    apt_get_install(repo_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file for repositories that use catkin
    print("Removing the CMakeLists.txt file generated by rosinstall")
    os.remove(os.path.join(repo_sourcespace, 'CMakeLists.txt'))
    print("Create a new CMakeLists.txt file using catkin")

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
        print("Build catkin workspace")
        call("catkin_init_workspace %s" % repo_sourcespace, ros_env)
        repos_test_results_dir = os.path.join(test_results_dir, 'repos')
        call("cmake %s -DCATKIN_TEST_RESULTS_DIR=%s" % (repo_sourcespace, repos_test_results_dir), ros_env)
        #ros_env_repo = get_ros_env(os.path.join(repo_buildspace, 'devel/setup.bash'))

        # build repositories and tests
        print("Build repo list")
        call("make", ros_env)
        call("make tests", ros_env)

        # get the repositories test and run dependencies
        print("Get test and run dependencies of repo list")
        repo_test_dependencies = get_dependencies(repo_sourcespace, build_depends=False, test_depends=True)
        print("Install test and run dependencies of repo list: %s" % (', '.join(repo_test_dependencies)))
        apt_get_install(repo_test_dependencies, rosdep_resolver, sudo)

        # get environment after installing test and run dependencies
        ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)

        # run tests
        print("Test repo list")
        call("make run_tests", ros_env)

        # anything after this should build on this env
        ros_env = get_ros_env(os.path.join(repo_buildspace, 'devel/setup.bash'))

    else:
        print("Build workspace with non-catkin packages in isolation")
        # work around catkin_make_isolated issue (at least with version 0.5.65 of catkin)
        os.makedirs(os.path.join(repo_buildspace, 'devel_isolated'))
        call('catkin_make_isolated --source %s --install-space install_isolated --install' % repo_sourcespace, ros_env)
        setup_file = os.path.join(repo_buildspace, 'install_isolated', 'setup.sh')
        # anything after this should build on this env
        ros_env = get_ros_env(setup_file)

    # don't do depends-on on things not in release
    not_in_release = set(repo_list) - set(release.repositories.keys())
    if not_in_release:
        print("Removed [%s] repositories which are not in the " %
              ', '.join(sorted(not_in_release)),
              "release file for depends-on testing")
        repo_list = list(set(repo_list) - not_in_release)

    # see if we need to do more work or not
    if not test_depends_on:
        print("We're not testing the depends-on repositories")
        ensure_test_results(test_results_dir)
        return

    # get repo_list depends-on list
    print("Get list of wet repositories that build-depend on repo list: %s" % ', '.join(repo_list))
    walker = DependencyWalker(release)
    depends_on = set([])
    try:
        for repo_name in repo_list:
            print('repo_name', repo_name)
            repo = release.repositories[repo_name]
            for pkg_name in repo.package_names:
                print('pkg_name', pkg_name)
                depends_on |= walker.get_recursive_depends_on(pkg_name, ['buildtool', 'build'], ignore_pkgs=depends_on)
                print('depends_on', depends_on)
        # remove all packages which are already in the workspace
        from catkin_pkg.packages import find_packages
        pkgs = find_packages(repo_sourcespace)
        depends_on -= set([pkg.name for pkg in pkgs.values()])
    except RuntimeError:
        print("Exception %s: If you are not in the rosdistro and only in the devel",
              " builds there will be no depends on")
        depends_on = set([])

    print("Build depends_on list of pkg list: %s" % (', '.join(depends_on)))
    if len(depends_on) == 0:
        print("No wet packages depend on our repo list. Test finished here")
        ensure_test_results(test_results_dir)
        return

    # install depends_on packages from source from release repositories
    rosinstall = ''
    non_catkin_pkgs = []
    for pkg_name in depends_on:
        repo = release.repositories[release.packages[pkg_name].repository_name]
        if repo.version is None:
            continue
        pkg_xml = release.get_package_xml(pkg_name)
        if pkg_xml is None:
            raise BuildException('Could not retrieve package.xml for package "%s" from rosdistro cache' % pkg_name)
        try:
            pkg = parse_package_string(pkg_xml)
        except InvalidPackage as e:
            raise BuildException('package.xml for package "%s" from rosdistro cache is invalid: %s' % (pkg_name, e))
        if _is_non_catkin_package(pkg):
            non_catkin_pkgs.append(pkg.name)
        rosinstall += _generate_rosinstall_for_pkg(repo, pkg_name)

    if non_catkin_pkgs:
        print('Non-catkin packages depend on our repo list (%s). Skipping depends_on packages here' % ', '.join(sorted(non_catkin_pkgs)))
        create_test_result(test_results_dir, failure='Non-catkin packages depend on the repos (%s). Skip building and testing depends_on packages.' % ', '.join(sorted(non_catkin_pkgs)))
        return

    print("Rosinstall for depends_on:\n %s" % rosinstall)
    with open(workspace + "/depends_on.rosinstall", 'w') as f:
        f.write(rosinstall)
    print("Created rosinstall file for depends on")

    # install all repository and system dependencies of the depends_on list
    print("Install all depends_on from source: %s" % (', '.join(depends_on)))
    os.makedirs(dependson_sourcespace)
    call("rosinstall --catkin %s %s/depends_on.rosinstall" % (dependson_sourcespace, workspace))

    # check if depends_on workspace contains only package built with catkin
    non_catkin_pkgs = _get_non_catkin_packages(dependson_sourcespace)
    if non_catkin_pkgs:
        print('Non-catkin packages depend on our repo list (%s). Skipping depends_on packages here' % ', '.join(sorted(non_catkin_pkgs)))
        create_test_result(test_results_dir, failure='Non-catkin packages depend on the repos (%s). Skip building and testing depends_on packages.' % ', '.join(sorted(non_catkin_pkgs)))
        return

    # get build and test dependencies of depends_on list
    dependson_build_dependencies = []
    for d in get_dependencies(dependson_sourcespace, build_depends=True, test_depends=False):
        print("  Checking dependency %s" % d)
        if d in dependson_build_dependencies:
            print("    Already in dependson_build_dependencies")
        if d in depends_on:
            print("    Is a direct dependency of the repo list, and is installed from source")
        if d in repo_list:
            print("    Is one of the repositories tested")
        if not d in dependson_build_dependencies and not d in depends_on and not d in repo_list:
            dependson_build_dependencies.append(d)
    print("Build dependencies of depends_on list are %s" % (', '.join(dependson_build_dependencies)))
    dependson_test_dependencies = []
    for d in get_dependencies(dependson_sourcespace, build_depends=False, test_depends=True):
        if not d in dependson_test_dependencies and not d in depends_on and not d in repo_list:
            dependson_test_dependencies.append(d)
    print("Test dependencies of depends_on list are %s" % (', '.join(dependson_test_dependencies)))

    # install build dependencies
    print("Install all build dependencies of the depends_on list")
    apt_get_install(dependson_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file again
    print("Removing the CMakeLists.txt file generated by rosinstall")
    os.remove(os.path.join(dependson_sourcespace, 'CMakeLists.txt'))
    os.makedirs(dependson_buildspace)
    os.chdir(dependson_buildspace)
    print("Create a new CMakeLists.txt file using catkin")
    call("catkin_init_workspace %s" % dependson_sourcespace, ros_env)
    depends_on_test_results_dir = os.path.join(test_results_dir, 'depends_on')
    call("cmake %s -DCATKIN_TEST_RESULTS_DIR=%s" % (dependson_sourcespace, depends_on_test_results_dir), ros_env)
    #ros_env_depends_on = get_ros_env(os.path.join(dependson_buildspace, 'devel/setup.bash'))

    # build repositories
    print("Build depends-on packages")
    call("make", ros_env)

    # install test dependencies
    print("Install all test dependencies of the depends_on list")
    apt_get_install(dependson_test_dependencies, rosdep_resolver, sudo)

    # test repositories
    print("Test depends-on packages")
    call("make run_tests", ros_env)
    ensure_test_results(test_results_dir)


def extract_notification_recipients(path):
    from catkin_pkg.packages import find_packages
    pkgs = find_packages(path)
    notification_recipients = set([])
    for pkg in pkgs.values():
        for m in pkg.maintainers:
            notification_recipients.add(m.email)
    if notification_recipients:
        print('Notification recipients: %s' % ' '.join(sorted(notification_recipients)))


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
    print("Parsing rosdistro file for %s" % ros_distro)
    distro = rosdistro.RosDistro(ros_distro)
    print("Parsing devel file for %s" % ros_distro)
    devel = rosdistro.DevelDistro(ros_distro)

    # Create rosdep object
    print("Create rosdep object")
    rosdep_resolver = rosdep.RosDepResolver(ros_distro, sudo, no_chroot)

    # download the repo_list from source
    print("Creating rosinstall file for repo list")
    rosinstall = ""
    for repo, version in zip(repo_list, version_list):
        if version == 'devel':
            if repo not in devel.repositories:
                raise BuildException("Repository %s does not exist in Devel Distro" % repo)
            print("Using devel distro file to download repositories")
            rosinstall += devel.repositories[repo].get_rosinstall()
        else:
            if repo not in distro.get_repositories():
                raise BuildException("Repository %s does not exist in Ros Distro" % repo)
            if version in ['latest', 'master']:
                print("Using latest release distro file to download repositories")
                rosinstall += distro.get_rosinstall(repo, version='master')
            else:
                print("Using version %s of release distro file to download repositories" % version)
                rosinstall += distro.get_rosinstall(repo, version)
    print("rosinstall file for all repositories: \n %s" % rosinstall)
    with open(os.path.join(workspace, "repo.rosinstall"), 'w') as f:
        f.write(rosinstall)
    print("Install repo list from source")
    os.makedirs(repo_sourcespace)
    call("rosinstall %s %s/repo.rosinstall --catkin" % (repo_sourcespace, workspace))

    # get the repositories build dependencies
    print("Get build dependencies of repo list")
    repo_build_dependencies = get_dependencies(repo_sourcespace, build_depends=True, test_depends=False)
    print("Install build dependencies of repo list: %s" % (', '.join(repo_build_dependencies)))
    apt_get_install(repo_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file for repositories that use catkin
    print("Removing the CMakeLists.txt file generated by rosinstall")
    os.remove(os.path.join(repo_sourcespace, 'CMakeLists.txt'))
    print("Create a new CMakeLists.txt file using catkin")
    ros_env = get_ros_env('/opt/ros/%s/setup.bash' % ros_distro)
    call("catkin_init_workspace %s" % repo_sourcespace, ros_env)
    test_results_dir = os.path.join(workspace, 'test_results')
    repos_test_results_dir = os.path.join(test_results_dir, 'repos')
    os.makedirs(repo_buildspace)
    os.chdir(repo_buildspace)
    call("cmake %s -DCATKIN_TEST_RESULTS_DIR=%s" % (repo_sourcespace, repos_test_results_dir), ros_env)
    #ros_env_repo = get_ros_env(os.path.join(repo_buildspace, 'devel/setup.bash'))

    # build repositories and tests
    print("Build repo list")
    call("make", ros_env)
    call("make tests", ros_env)

    # get the repositories test and run dependencies
    print("Get test and run dependencies of repo list")
    repo_test_dependencies = get_dependencies(repo_sourcespace, build_depends=False, test_depends=True)
    print("Install test and run dependencies of repo list: %s" % (', '.join(repo_test_dependencies)))
    apt_get_install(repo_test_dependencies, rosdep_resolver, sudo)

    # run tests
    print("Test repo list")
    call("make run_tests", ros_env)

    # see if we need to do more work or not
    if not test_depends_on:
        print("We're not testing the depends-on repositories")
        ensure_test_results(test_results_dir)
        return

    # get repo_list depends-on list
    print("Get list of wet repositories that build-depend on repo list %s" % ', '.join(repo_list))
    depends_on = []
    try:
        for d in distro.get_depends_on(repo_list)['build'] + distro.get_depends_on(repo_list)['buildtool']:
            if not d in depends_on and not d in repo_list:
                depends_on.append(d)
    except RuntimeError:
        print("Exception %s: If you are not in the rosdistro and only in the devel",
              " builds there will be no depends on")
        depends_on = []

    print("Build depends_on list of repo list: %s" % (', '.join(depends_on)))
    if len(depends_on) == 0:
        print("No wet repositories depend on our repo list. Test finished here")
        ensure_test_results(test_results_dir)
        return

    # install depends_on repositories from source
    rosinstall = distro.get_rosinstall(depends_on)
    print("Rosinstall for depends_on:\n %s" % rosinstall)
    with open(workspace + "/depends_on.rosinstall", 'w') as f:
        f.write(rosinstall)
    print("Created rosinstall file for depends on")

    # install all repository and system dependencies of the depends_on list
    print("Install all depends_on from source: %s" % (', '.join(depends_on)))
    os.makedirs(dependson_sourcespace)
    call("rosinstall --catkin %s %s/depends_on.rosinstall" % (dependson_sourcespace, workspace))

    # get build and test dependencies of depends_on list
    dependson_build_dependencies = []
    for d in get_dependencies(dependson_sourcespace, build_depends=True, test_depends=False):
        print("  Checking dependency %s" % d)
        if d in dependson_build_dependencies:
            print("    Already in dependson_build_dependencies")
        if d in depends_on:
            print("    Is a direct dependency of the repo list, and is installed from source")
        if d in repo_list:
            print("    Is on of the repositories tested")
        if not d in dependson_build_dependencies and not d in depends_on and not d in repo_list:
            dependson_build_dependencies.append(d)
    print("Build dependencies of depends_on list are %s" % (', '.join(dependson_build_dependencies)))
    dependson_test_dependencies = []
    for d in get_dependencies(dependson_sourcespace, build_depends=False, test_depends=True):
        if not d in dependson_test_dependencies and not d in depends_on and not d in repo_list:
            dependson_test_dependencies.append(d)
    print("Test dependencies of depends_on list are %s" % (', '.join(dependson_test_dependencies)))

    # install build dependencies
    print("Install all build dependencies of the depends_on list")
    apt_get_install(dependson_build_dependencies, rosdep_resolver, sudo)

    # replace the CMakeLists.txt file again
    print("Removing the CMakeLists.txt file generated by rosinstall")
    os.remove(os.path.join(dependson_sourcespace, 'CMakeLists.txt'))
    os.makedirs(dependson_buildspace)
    os.chdir(dependson_buildspace)
    print("Create a new CMakeLists.txt file using catkin")
    call("catkin_init_workspace %s" % dependson_sourcespace, ros_env)
    depends_on_test_results_dir = os.path.join(test_results_dir, 'depends_on')
    call("cmake %s -DCATKIN_TEST_RESULTS_DIR=%s" % (dependson_sourcespace, depends_on_test_results_dir), ros_env)
    #ros_env_depends_on = get_ros_env(os.path.join(dependson_buildspace, 'devel/setup.bash'))

    # build repositories
    print("Build depends-on repositories")
    call("make", ros_env)

    # install test dependencies
    print("Install all test dependencies of the depends_on list")
    apt_get_install(dependson_test_dependencies, rosdep_resolver, sudo)

    # test repositories
    print("Test depends-on repositories")
    call("make run_tests", ros_env)
    ensure_test_results(test_results_dir)


def _generate_rosinstall_for_pkg(repo, pkg_name):
    from rosdistro.manifest_provider import get_release_tag
    return _generate_rosinstall_for_pkg_version(repo, pkg_name, get_release_tag(repo, pkg_name))


def _generate_rosinstall_for_pkg_version(repo, pkg_name, version):
    import yaml
    repo_data = {
        'local-name': pkg_name,
        'uri': repo.url,
        'version': version
    }
    return yaml.safe_dump([{repo.type: repo_data}], default_style=False)


def _generate_rosinstall_for_repo(repo, version=None):
    import yaml
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

    if len(args) <= 2 or len(args) % 2 != 1:
        print("Usage: %s ros_distro repo1 version1 repo2 version2 ..." % sys.argv[0])
        print(" - with ros_distro the name of the ros distribution (e.g. 'fuerte' or 'groovy')")
        print(" - with repo the name of the repository")
        print(" - with version 'latest', 'devel', or the actual version number (e.g. 0.2.5).")
        raise BuildException("Wrong arguments for test_repositories script")

    ros_distro = args[0]

    repo_list = [args[i] for i in range(1, len(args), 2)]
    version_list = [args[i + 1] for i in range(1, len(args), 2)]
    workspace = os.environ['WORKSPACE']

    print("Running test_repositories test on distro %s and repositories %s" % (ros_distro,
                                                                               ', '.join(["%s (%s)" % (r, v) for r, v in zip(repo_list, version_list)])))
    test_repositories(ros_distro, repo_list, version_list, workspace, test_depends_on=options.depends_on)


if __name__ == '__main__':
    # global try
    try:
        main()
        print("test_repositories script finished cleanly")

    # global catch
    except BuildException as ex:
        print(ex.msg)

    except Exception as ex:
        print("test_repositories script failed. Check out the console output above for details.")
        raise
