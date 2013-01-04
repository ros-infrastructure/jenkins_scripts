#!/usr/bin/env python
import os
from apt_parser import parse_apt
import sys
import os
import shutil
import optparse 
import subprocess
import traceback
import numpy
import yaml
import codecs
import roslib; roslib.load_manifest("job_generation")
from roslib import stack_manifest
import rosdistro
from jobs_common import *
import urllib2

env= get_environment()
env['INSTALL_DIR'] = os.getcwd()

def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'path' in ops:
        parser.add_option('--path', dest = 'path', default=None, action='store',
                          help='path to scan')
    if 'doc' in ops:
        parser.add_option('--doc', dest = 'doc', default='doc', action='store',
                          help='doc folder')
    if 'csv' in ops:
        parser.add_option('--csv', dest = 'csv', default='csv', action='store',
                          help='csv folder')
    if 'config' in ops:
        parser.add_option('--config', dest = 'config', default=None, action='store',
                          help='config file')
	
    if 'distro' in ops:
        parser.add_option('--distro', dest = 'distro', default=None, action='store',
                          help='distro name')    

    if 'stack' in ops:
        parser.add_option('--stack', dest = 'stack', default=None, action='store',
                          help='stack name')  
                          
    (options, args) = parser.parse_args()

    # check if required arguments are there
    for r in required:
        if not eval('options.%s'%r):
            print 'You need to specify "--%s"'%r
            return (None, args)

    return (options, args)
    

def all_files(directory):
    for path, dirs, files in os.walk(directory):
        for f in files:
            yield os.path.abspath(os.path.join(path, f))
            
class Metric:
    def __init__(self, name):
        self.name = name
        self.data = []
        self.uniqueids = {}
        self.histogram_labels = []
        self.histogram_counts = []
	self.histogram_names = []
	self.histogram_filenames = []
	self.uri = []
                    
class ExportYAML:
    def __init__(self, config, path, doc, csv, distro, stack):
        self.config = config
        self.path = path
        self.distro = distro
	self.stack = stack
        self.doc = doc
	if os.path.exists(doc):
	    shutil.rmtree(doc)
        os.makedirs(doc)
          
        self.csv = csv
	if os.path.exists(csv):
	    shutil.rmtree(csv)
        os.makedirs(csv)
          
        self.stack_files = [f for f in all_files(self.path)
            if f.endswith('stack.xml')]

        self.stack_dirs = [os.path.dirname(f) for f in self.stack_files]
            
        self.package_files = [f for f in all_files(self.path)
            if f.endswith('manifest.xml')]

        self.package_dirs = [os.path.dirname(f) for f in self.package_files]

        self.met_files = [f for f in all_files(self.path)
            if f.endswith('.met') and f.find('CompilerIdCXX')<0 and f.find('CompilerIdC')<0 and f.find('third_party')<0]
        
        self.metrics = {}

    def safe_encode(self, d):
        d_copy = d.copy()
        for k, v in d_copy.iteritems():
            if isinstance(v, basestring):
                try:
                    d[k] = v.encode("utf-8")
                except UnicodeDecodeError, e:
                    print >> sys.stderr, "error: cannot encode value for key", k
                    d[k] = ''
            elif type(v) == list:
                try:
                    d[k] = [x.encode("utf-8") for x in v]
                except UnicodeDecodeError, e:
                    print >> sys.stderr, "error: cannot encode value for key", k
                    d[k] = []
        return d
    
    def get_package(self, met_file):
        for package_dir in self.package_dirs:
            if met_file.find(package_dir)>=0:
                return os.path.basename(package_dir)
        return ''
    
    def get_package_dir(self, met_file):
        for package_dir in self.package_dirs:
            if met_file.find(package_dir)>=0:
                return package_dir
        return ''
        
    def get_stack(self, met_file):
        for stack_dir in self.stack_dirs:
            if met_file.find(stack_dir)>=0:
                return os.path.basename(stack_dir)
        return ''
    
    def get_stack_dir(self, met_file):
        for stack_dir in self.stack_dirs:
            if met_file.find(stack_dir)>=0:
                return stack_dir
        return ''

    def histogram(self, metric, numbins, minval, maxval, data_type):
        if not metric in self.metrics:
            return;
        data = []
    	data_param_names = []
	data_param_filenames = []
	array = self.metrics[metric].data
	for d in array:
            data.append(float(d[4]))
	    data_param_names.append(str(d[2]))
	    data_param_filenames.append(str(d[5]))
        bin_size = (float(maxval) - float(minval))/(int(numbins))
        histogram_bins = [float(minval)+bin_size*x for x in range(numbins+1)]
        histogram_labels = []
        if data_type == 'int':
            histogram_labels = [repr(int(x)) for x in histogram_bins]
        else:
            histogram_labels = ['%.2g'%x for x in histogram_bins]
            
        # modify open-ended element
        histogram_bins.append(sys.float_info.max)
        histogram_labels[-1] = '>' + histogram_labels[-1]
        
        (hist,bin_edges) = numpy.histogram(data, histogram_bins)

	# Append data to histogram 
        m = self.metrics[metric]
        for i in range(len(hist)):
            m.histogram_counts.append(hist[i])
            m.histogram_labels.append(histogram_labels[i])

	for i in range(len(data_param_names)):
	    m.histogram_names.append(data_param_names[i])

	for i in range(len(data_param_filenames)):
	    m.histogram_filenames.append(data_param_filenames[i])

	# Parse distro file
        rosdistro_obj = rosdistro.Distro(get_rosdistro_file(self.distro))
	
	# Get uri
	vcs = rosdistro_obj.stacks[self.stack].vcs_config
	if vcs.type == 'svn':
	    uri = vcs.anon_dev
	elif vcs.type == 'hg' or vcs.type == 'git' or vcs.type == 'bzr':
	    uri = vcs.anon_repo_uri
	
	# Append uri to histogram
	m.uri.append(uri)

    def process_met_file(self, met_file):
        stack = self.get_stack(met_file)
        package = self.get_package(met_file)
        package_dir = self.get_package_dir(met_file)
        stack_dir = self.get_stack_dir(met_file)
        filename = ''
        name = ''   
        met = open(met_file,'r')
        while met:
            l = met.readline()
            if not l:
                break
            l = l.replace('\n','')
            if l.startswith('<S>'): 
                tokens = l.split(' ')
                if len(tokens)<2: continue
                cmd = tokens[0]
                if len(cmd) < 5: continue
                cmd = cmd[3:]
                val = tokens[1]
                if cmd == 'STFIL':
                    filename = val
                    continue
                if cmd == 'STNAM':
                    name = val
                    continue
                # filter out entries outside of the current stack
                if filename.find(stack_dir) < 0: continue
                # add metric to list of not already there yet
                metric_name = cmd
                if not metric_name in self.metrics:
                    self.metrics[metric_name] = Metric(metric_name)
                # add entry
                metric = self.metrics[metric_name]
                #metric.data.append([stack,package,name,cmd,val,filename])
                uniqueid = filename+name
                if not uniqueid in metric.uniqueids:                        
                    metric.data.append([stack,package,name,cmd,val,filename])
                    metric.uniqueids[uniqueid] = True
        
        met.close()
        return ''
        
    def create_code_quality_yaml(self):
        filename = self.doc + '/' + 'code_quality.yaml'
        d = {}
        for m in self.config['metrics'].keys():
            if not m in self.metrics: 
                continue
            metric = self.metrics[m]
            config = self.config['metrics'][m]
            config['histogram_bins'] = [b for b in metric.histogram_labels] 
            config['histogram_counts'] = [int(b) for b in metric.histogram_counts]
	    config['histogram_names'] = [b for b in metric.histogram_names] 
	    config['histogram_filenames'] = [b for b in metric.histogram_filenames] 
	    config['uri'] = [b for b in metric.uri]  
	    d[m] = config
            
        #print yaml.dump(d)
        
        # encode unicode entries
        d = self.safe_encode(d)
        
        with codecs.open(filename, mode='w', encoding='utf-8') as f:
            f.write(yaml.safe_dump(d, default_style="'")) 
             
    def create_csv(self):
        for m in self.config['metrics'].keys():
            if not m in self.metrics: 
                continue
            filename = self.csv + '/' + m + '.csv' 
            data = self.metrics[m].data
            f = open(filename,"w")
            for d in data:
                string = ';'.join(d)
                f.write(string + '\n') 
            f.close()
            
    def create_csv_hist(self):
        for m in self.config['metrics'].keys():
            if not m in self.metrics: 
                continue
            metric = self.metrics[m]    
            filename = self.csv + '/' + m + '_hist.csv' 
            labels = metric.histogram_labels
            counts = metric.histogram_counts
            f = open(filename,"w")
            for i in range(len(counts)):
                string = ';'.join([labels[i],repr(counts[i])])
                f.write(string + '\n')
            f.close()  
               
    def create_loc(self):
        filename = self.doc + '/' + 'code_quantity.yaml'
        print "os.environ['WORKSPACE']: %s"%(os.environ['WORKSPACE'])
	helper = subprocess.Popen(('%s/jenkins_scripts/cloc.pl %s --not-match-d=build --yaml --out %s'%(os.environ['WORKSPACE'],self.path, filename)).split(' '),env=env)
        helper.communicate()
                      
    def export(self):
        # process all met files
        for met in self.met_files:
            # print met
            self.process_met_file(met)
            
        # create histograms
	for m in self.config['metrics'].keys():
            if not m in self.metrics: 
                continue
            config = self.config['metrics'][m]
	    self.histogram(m, config['histogram_num_bins'], config['histogram_minval'], config['histogram_maxval'], config['data_type'])

        # create yaml
        self.create_code_quality_yaml()
        
        # create csv
        self.create_csv()
        self.create_csv_hist()
        
        # export code lines of code
        self.create_loc()
        
if __name__ == '__main__':   
    (options, args) = get_options(['path', 'config', 'distro', 'stack'], ['doc','csv'])
    if not options:
        exit(-1)
    
    with open(options.config) as f:
        config = yaml.load(f)
    
    # get stacks  
    print 'Exporting stacks to yaml/csv'      
    stack_files = [f for f in all_files(options.path) if f.endswith('stack.xml')]
    stack_dirs = [os.path.dirname(f) for f in stack_files]
    for stack_dir in stack_dirs:
        stack = os.path.basename(stack_dir)
        print stack_dir
        doc_dir = options.doc + '/' + stack
        csv_dir = options.csv + '/' + stack
        if os.path.isdir(doc_dir):
            shutil.rmtree(doc_dir)    
        os.makedirs(doc_dir)
	if os.path.isdir(csv_dir):
            shutil.rmtree(csv_dir)    
        os.makedirs(csv_dir)
        hh = ExportYAML(config, stack_dir, doc_dir, csv_dir, options.distro, options.stack)
        hh.export()
	
	        
    # get packages
    print 'Exporting packages to yaml/csv'  
    package_files = [f for f in all_files(options.path) if f.endswith('manifest.xml')]
    package_dirs = [os.path.dirname(f) for f in package_files]
    for package_dir in package_dirs:
        package = os.path.basename(package_dir)
        print package
        doc_dir = options.doc + '/' + package
        csv_dir = options.csv + '/' + package
        if os.path.isdir(doc_dir):
            shutil.rmtree(doc_dir)    
        os.makedirs(doc_dir)
	if os.path.isdir(csv_dir):
            shutil.rmtree(csv_dir)    
        os.makedirs(csv_dir)
        hh = ExportYAML(config, package_dir, doc_dir, csv_dir, options.distro, options.stack)
        hh.export()
	    
