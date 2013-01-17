#!/bin/bash -ex
/bin/echo '^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ run_analysis.sh ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'

# Add ros sources to apt
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu '$OS_PLATFORM' main" > /etc/apt/sources.list.d/ros-latest.list'
wget http://packages.ros.org/ros.key -O $WORKSPACE/ros.key
apt-key add $WORKSPACE/ros.key
sudo apt-get update


# install stuff we need
echo "Installing Debian packages we need for running this script"
if [ "$ROS_DISTRO" == 'electric' ] ; then
    echo "Using rosdistro electric"
    sudo apt-get install apt-utils ia32-libs python-rosinstall python-rospkg python-tk openssh-server ros-electric-ros-release --yes
    source /opt/ros/$ROS_DISTRO/setup.sh
    sudo cp $HOME/chroot_configs/rostoolchain.cmake /opt/ros/$ROS_DISTRO/ros/rostoolchain.cmake

    # call analysis
    python $WORKSPACE/jenkins_scripts/analyze.py $ROS_DISTRO $STACK_NAME

elif [ "$ROS_DISTRO" == 'fuerte' ] ; then
    echo "Using rosdistro fuerte"
    # ia32-libs
    sudo apt-get install apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-fuerte-ros --yes
    source /opt/ros/$ROS_DISTRO/setup.bash
    svn co https://code.ros.org/svn/ros/stacks/ros_release/trunk $HOME/fuerte_workspace/ros_release
    export ROS_PACKAGE_PATH=$HOME/fuerte_workspace:$ROS_PACKAGE_PATH
    cd $HOME/fuerte_workspace/ros_release && rosmake
    sudo cp $HOME/chroot_configs/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake

    # call analysis
    python $WORKSPACE/jenkins_scripts/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME

elif [ "$ROS_DISTRO" == 'groovy' ] ; then
    echo "Using rosdistro groovy"
    # ia32-libs
    sudo apt-get install apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-groovy-ros-base --yes
    sudo rosdep init
    rosdep update
    source /opt/ros/$ROS_DISTRO/setup.bash
    #svn co https://code.ros.org/svn/ros/stacks/ros_release/trunk $HOME/groovy_workspace/ros_release
    svn co https://code.ros.org/svn/ros/stacks/ros_release/branches/groovy/ $HOME/groovy_workspace/ros_release
    export ROS_PACKAGE_PATH=$HOME/groovy_workspace:$ROS_PACKAGE_PATH
    cd $HOME/groovy_workspace/ros_release && rosmake
    sudo cp $HOME/chroot_configs/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/core/rosbuild/rostoolchain.cmake
    cd $WORKSPACE
    # call analysis
    python $WORKSPACE/jenkins_scripts/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME
fi



source $HOME/chroot_configs/set_qacpp_path.sh
