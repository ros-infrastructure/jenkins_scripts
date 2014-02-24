
import os

from common import apt_get_install, call, check_output


class RosDepResolver:
    def __init__(self, ros_distro, sudo=False, no_chroot=False):
        self.r2a = {}
        self.a2r = {}
        self.env = os.environ
        self.env['ROS_DISTRO'] = ros_distro

        if no_chroot:
            print("Skip initializing and updating rosdep database")
        else:
            print("Ininitalize rosdep database")
            apt_get_install(['lsb-release', 'python-rosdep'], sudo=sudo)
            try:
                call("rosdep init", self.env)
            except:
                print("Rosdep is already initialized")
            call("rosdep update", self.env)

        print("Building dictionaries from a rosdep's db")
        raw_db = check_output("rosdep db", self.env, verbose=False).split('\n')

        for entry in raw_db:
            split_entry = entry.split(' -> ')
            if len(split_entry) < 2:
                continue
            ros_entry = split_entry[0]
            apt_entries = split_entry[1].split(' ')
            self.r2a[ros_entry] = apt_entries
            for a in apt_entries:
                self.a2r[a] = ros_entry

    def to_aptlist(self, ros_entries):
        res = []
        for r in ros_entries:
            for a in self.to_apt(r):
                if not a in res:
                    res.append(a)
        return res

    def to_ros(self, apt_entry):
        if apt_entry not in self.a2r:
            print("Could not find %s in rosdep keys. Rosdep knows about these keys: %s" % (apt_entry, ', '.join(sorted(self.a2r.keys()))))
        return self.a2r[apt_entry]

    def to_apt(self, ros_entry):
        if ros_entry not in self.r2a:
            print("Could not find %s in keys. Have keys %s" % (ros_entry, ', '.join(sorted(self.r2a.keys()))))
        return self.r2a[ros_entry]

    def has_ros(self, ros_entry):
        return ros_entry in self.r2a

    def has_apt(self, apt_entry):
        return apt_entry in self.a2r
