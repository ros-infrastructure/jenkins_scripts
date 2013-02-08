#!/usr/bin/python

import urllib
import yaml


def parse_package(package_string, rosdistro):
    depends = []
    for l in package_string.splitlines():
        if 'Package: ' in l:
            package = deb_to_stack(l.split('Package: ')[1], rosdistro)
        elif 'Depends' in l:
            dep_str = l.split('Depends: ')[1]
            for d in dep_str.split(', '):
                if '(' in d:
                    dep = deb_to_stack(d.split(' ')[0], rosdistro)
                    if dep:
                        depends.append(dep)
        elif 'Description: Meta package for' in l:
            return (None, None)  # skip variant meta packages

    return (package, depends)



def deb_to_stack(deb_name, rosdistro):
    if not deb_name.startswith('ros-%s'%rosdistro):
        return None
    return '_'.join(deb_name.split('-')[2:])



class AptParser:
    def __init__(self, string, rosdistro):
        self.depends_list = {}
        self.depends_on_list = {}
        
        for package in string.split('Package: '):
            if len(package) > 0:
                (package, depends) = parse_package('Package: '+package, rosdistro)
                if package:
                    if not package in self.depends_on_list:
                        self.depends_on_list[package] = []

                    self.depends_list[package] = depends
                    for d in depends:
                        if d in self.depends_on_list:
                            if not package in self.depends_on_list[d]:
                                self.depends_on_list[d].append(package)
                        else:
                            self.depends_on_list[d] = [package]

    def depends(self, pkg):
        return self._get_one_depth(pkg, self.depends_list)

    def depends_on(self, pkg):
        return self._get_one_depth(pkg, self.depends_on_list)

    def depends_all(self, pkg):
        return self._get_all_depth(pkg, self.depends_list)

    def depends_on_all(self, pkg):
        return self._get_all_depth(pkg, self.depends_on_list)

    def has_debian_package(self, pkg):
        if type(pkg) != list:
            pkg = [pkg]
        for p in pkg:
            if not p in self.depends_list:
                return False
        return True


    def _get_all_depth(self, pkg, my_list):
        res = []
        for p in self._get_one_depth(pkg, my_list):
            self._add_recursive(p, res, my_list)
        return res

    def _get_one_depth(self, pkg, my_list):
        if (type(pkg) != list):
            return my_list[pkg]
        res = []
        for p in pkg:
            for d in my_list[p]:
                if not d in res:
                    res.append(d)
        return res
        

    def _add_recursive(self, pkg, res_list, my_list):
        if not pkg in res_list:
            res_list.append(pkg)
            for p in self._get_one_depth(pkg, my_list):
                self._add_recursive(p, res_list, my_list)

        

def parse_apt(ubuntudistro, arch, rosdistro):
    url_name = 'http://packages.ros.org/ros-shadow-fixed/ubuntu/dists/%s/main/binary-%s/Packages'%(ubuntudistro, arch)
    parser = AptParser(urllib.urlopen(url_name).read(), rosdistro)
    return parser



def main():
    parser = parse_apt('lucid', 'amd64', 'diamondback')

    dep = parser.depends('robot_model')
    dep.sort()
    print dep

    dep_all = parser.depends_all('robot_model')
    dep_all.sort()
    print dep_all

    dep_on = parser.depends_on('robot_model')
    dep_on.sort()
    print dep_on

    dep_on_all = parser.depends_on_all('robot_model')
    dep_on_all.sort()
    print dep_on_all




if __name__ == '__main__':
    main()
