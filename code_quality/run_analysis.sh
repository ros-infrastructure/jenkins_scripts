#!/bin/bash -ex
/bin/echo '^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ run_analysis.sh ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'

# Error exit function
function error_exit
{
    echo "$1" 1>&2
	exit 1
}

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
    if python $WORKSPACE/jenkins_scripts/code_quality/analyze.py $ROS_DISTRO $STACK_NAME; then
    	echo 'analyze.py passed'
    else
		error_exit "analyze.py failed!  Aborting."
	fi

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
    if python $WORKSPACE/jenkins_scripts/code_quality/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME; then
        echo 'analyze_fuerte_groovy.py passed'
    else
		error_exit "analyze_fuerte_groovy.py failed!  Aborting."
	fi

elif [ "$ROS_DISTRO" == 'groovy' ] && [ "$BUILD_SYSTEM" == 'dry' ] ; then
    echo "Using rosdistro groovy"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-groovy-ros-base --yes 
    sudo rosdep init
    rosdep update
    if ! source /opt/ros/$ROS_DISTRO/setup.bash; then
        error_exit "Canot source setup.bash!  Aborting."
    fi
    sudo easy_install ros-job-generation
    if sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake; then
        echo 'copied rostoolchain.cmake file successfully'
    else
        error_exit "Cannot copy rostoolchain.cmake!  Aborting."
    fi
    cd $WORKSPACE
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    if python $WORKSPACE/jenkins_scripts/code_quality/analyze_fuerte_groovy.py $ROS_DISTRO $STACK_NAME; then
        echo 'analyze_fuerte_groovy.py passed'
    else
    	error_exit "analyze_fuerte_groovy.py failed!  Aborting."
	fi

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
    if python $WORKSPACE/jenkins_scripts/code_quality/wet/analyze_wet.py $ROS_DISTRO $STACK_NAME 'latest'; then
        echo 'analyze_wet.py passed'
    else
        error_exit "analyze_wet.py failed!  Aborting."
	fi

elif [ "$ROS_DISTRO" == 'groovy' ] && [ "$BUILD_SYSTEM" == 'wet' ]; then
    echo "Using rosdistro groovy"
    sudo apt-get install ia32-libs apt-utils python-rosinstall python-rosdep python-rospkg python-tk openssh-server ros-groovy-ros-base --yes 
    if ! source /opt/ros/$ROS_DISTRO/setup.bash; then
        error_exit "Canot source setup.bash!  Aborting."
    fi
    sudo easy_install ros-job-generation
    if sudo cp $HOME/chroot_configs/rostoolchain_precise/rostoolchain.cmake /opt/ros/$ROS_DISTRO/share/ros/rostoolchain.cmake; then
        echo 'copied rostoolchain.cmake file successfully'
    else
        error_exit "Cannot copy rostoolchain.cmake!  Aborting."
    fi
    cd $WORKSPACE
    source $HOME/chroot_configs/set_qacpp_path.sh

    # call analysis
    if python $WORKSPACE/jenkins_scripts/code_quality/wet/analyze_wet.py $ROS_DISTRO $STACK_NAME 'latest'; then
        echo 'analyze_wet.py passed'
    else
        error_exit "analyze_wet.py failed!  Aborting."
    fi
fi
