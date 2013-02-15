#!/bin/bash -ex
/bin/echo '^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ run_analysis.sh ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'

# Add ros sources to apt
sudo sh -c 'echo "deb http://packages.ros.org/ros/ubuntu '$OS_PLATFORM' main" > /etc/apt/sources.list.d/ros-latest.list'
wget http://packages.ros.org/ros.key -O $WORKSPACE/ros.key
apt-key add $WORKSPACE/ros.key
sudo apt-get update


# DRY: install stuff we need 
echo "Installing Debian packages we need for running this script"
if [ "$ROS_DISTRO" == 'electric' ] && [ "$BUILD_SYSTEM" == 'dry' ] ; then
    echo "Using rosdistro electric"
    sudo apt-get install apt-utils ia32-libs python-rosinstall python-rospkg python-tk openssh-server ros-electric-ros-release --yes
    source /opt/ros/$ROS_DISTRO/setup.sh
    sudo cp $HOME/chroot_configs/rostoolchain_lucid/rostoolchain.cmake /opt/ros/$ROS_DISTRO/ros/rostoolchain.cmake
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    python $WORKSPACE/jenkins_scripts/code_quality/analyze.py $ROS_DISTRO $STACK_NAME

elif [ "$ROS_DISTRO" == 'fuerte' ] && [ "$BUILD_SYSTEM" == 'dry' ] ; then
    echo "Using rosdistro fuerte"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-fuerte-ros-comm --yes
    source /opt/ros/$ROS_DISTRO/setup.bash
    sudo rosdep init
    rosdep update
    sudo easy_install ros-job-generation
    if [ "$OS_PLATFORM" == 'precise' ] ; then
        sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake
    elif [ "$OS_PLATFORM" == 'lucid' ] ; then
        sudo cp $HOME/chroot_configs/rostoolchain_lucid/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake
    fi
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    python $WORKSPACE/jenkins_scripts/code_quality/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME

elif [ "$ROS_DISTRO" == 'groovy' ] && [ "$BUILD_SYSTEM" == 'dry' ] ; then
    echo "Using rosdistro groovy"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-groovy-bfl --yes 
    sudo rosdep init
    rosdep update
    source /opt/ros/$ROS_DISTRO/setup.bash
    sudo easy_install ros-job-generation
    sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake
    cd $WORKSPACE
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    python $WORKSPACE/jenkins_scripts/code_quality/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME


# WET: install stuff we need 
elif [ "$ROS_DISTRO" == 'fuerte' ] && [ "$BUILD_SYSTEM" == 'wet' ] ; then
    echo "Using rosdistro fuerte"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-fuerte-ros-comm --yes
    source /opt/ros/$ROS_DISTRO/setup.bash
    sudo easy_install ros-job-generation
    if [ "$OS_PLATFORM" == 'precise' ] ; then
        sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake
    elif [ "$OS_PLATFORM" == 'lucid' ] ; then
        sudo cp $HOME/chroot_configs/rostoolchain_lucid/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake
    fi
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    python $WORKSPACE/jenkins_scripts/code_quality/wet/analyze_wet.py $ROS_DISTRO $STACK_NAME 'latest'

elif [ "$ROS_DISTRO" == 'groovy' ] && [ "$BUILD_SYSTEM" == 'wet' ]; then
    echo "Using rosdistro groovy"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-groovy-bfl --yes 
    source /opt/ros/$ROS_DISTRO/setup.bash
    sudo easy_install ros-job-generation
    sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake 
    cd $WORKSPACE
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    python $WORKSPACE/jenkins_scripts/code_quality/wet/analyze_wet.py $ROS_DISTRO $STACK_NAME 'latest'
fi
