#! /usr/bin/env python

import sys
import yaml
import copy


#Replace vars with their actual values
def generate_full_rules(stack_name, stack_version, release_name, orig_rules):
    rules = copy.deepcopy(orig_rules)
    for name, conf in rules.iteritems():
        if name == 'svn' or name == 'hg' or name == 'git' or name == 'bzr':
            for key, value in conf.iteritems():
                value = value.replace('$STACK_NAME', stack_name or '')
                value = value.replace('$STACK_VERSION', stack_version or '')
                value = value.replace('$RELEASE_NAME', release_name or '')
                rules[name][key] = value

    return rules


def generate_new_format(rules):
    new_rules = {}
    for name, conf in rules.iteritems():
        if name == 'svn':
            new_rules['type'] = name
            new_rules['url'] = conf['dev']
        elif name == 'hg' or name == 'git' or name == 'bzr':
            new_rules['type'] = name
            if 'anon-uri' in conf:
                new_rules['url'] = conf['anon-uri']
            else:
                new_rules['url'] = conf['uri']
            new_rules['version'] = conf['dev-branch']
    return new_rules


def translate(filename, new_filename):
    with open(filename, 'r') as f:
        distro_yaml = yaml.load(f)

    release_name = distro_yaml['release']

    default_rules = distro_yaml['_rules'][distro_yaml['stacks']['_rules']]

    new_yaml = {}
    new_yaml['repositories'] = {}
    new_yaml['release-name'] = release_name
    new_yaml['type'] = 'doc'

    for stack, info in distro_yaml['stacks'].iteritems():
        #Skip the "_rules" stack since it's special
        if stack == '_rules':
            continue
        elif not '_rules' in info:
            rules_template = default_rules
        elif type(info['_rules']) == str:
            rules_template = distro_yaml['_rules'][info['_rules']]
        else:
            rules_template = info['_rules']

        rules = generate_full_rules(stack, info.get('version', None), release_name, rules_template)
        new_yaml['repositories'][stack] = generate_new_format(rules)

    with open(new_filename, 'w+') as f:
        print "Writing translated version to %s" % new_filename
        yaml.dump(new_yaml, f, default_flow_style=False)


if __name__ == '__main__':
    translate(sys.argv[1], sys.argv[2])
