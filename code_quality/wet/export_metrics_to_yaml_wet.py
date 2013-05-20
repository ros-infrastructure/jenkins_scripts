#!/usr/bin/env python
import os
import sys
sys.path.append('%s/jenkins_scripts/code_quality'%os.environ['WORKSPACE'])
from apt_parser import parse_apt
import os
import shutil
import optparse 
import subprocess
import traceback
import numpy
import yaml
import codecs
import urllib2
from time import gmtime, strftime

WIKI_SERVER_KEY_PATH = os.environ['HOME'] +'/chroot_configs/keypair.pem'
#ROS_WIKI_SERVER = 'ubuntu@ec2-184-169-231-58.us-west-1.compute.amazonaws.com:~/doc'
ROS_WIKI_SERVER = 'rosbuild@www.ros.org:/var/www/www.ros.org/html/metrics'

def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'path' in ops:
        parser.add_option('--path', dest = 'path', default=None, action='store',
                          help='path to build')
    if 'path_src' in ops:
        parser.add_option('--path_src', dest = 'path_src', default=None, action='store',
                          help='path_src to source')
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

    if 'uri_info' in ops:
        parser.add_option('--uri_info', dest = 'uri_info', default=None, action='store',
                          help='uri info')  
                                                    
    if 'uri' in ops:
        parser.add_option('--uri', dest = 'uri', default=None, action='store',
                          help='uri')  
                                                    
    if 'vcs_type' in ops:
        parser.add_option('--vcs_type', dest = 'vcs_type', default=None, action='store',
                          help='vcs_type')  
                          
    (options, args) = parser.parse_args()

    # check if required arguments are there
    for r in required:
        if not eval('options.%s'%r):
            print 'You need to specify "--%s"'%r
            return (None, args)

    return (options, args)
    

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
	self.histogram_affected = []
	self.histogram_filenames = []
	self.histogram_file_values = []
        self.metric_average = []
	self.uri = []
	self.uri_info = []
	self.vcs_type = [] 
	self.datetime = []
                    
class ExportYAML:
    def __init__(self, config, path, path_src, doc, csv, distro, stack, uri, uri_info, vcs_type):
        self.config = config
        self.path = path
        self.path_src = path_src
        self.distro = distro
	self.stack = stack
        self.doc = doc
        self.uri = uri
        self.uri_info = uri_info
        self.vcs_type = vcs_type
	if os.path.exists(doc):
	    shutil.rmtree(doc)
        os.makedirs(doc)
          
        self.csv = csv
	if os.path.exists(csv):
	    shutil.rmtree(csv)
        os.makedirs(csv)
          
        self.stack_files = [f for f in all_files(self.path)
            if f.endswith('CMakeCache.txt')]

        self.stack_dirs = [os.path.dirname(f) for f in self.stack_files]
            
        self.package_files = [f for f in all_files(self.path)
            if f.endswith('manifest.xml')]

        self.package_dirs = [os.path.dirname(f) for f in self.package_files]

	#print "path: %s"%(self.path)
        self.met_files = [f for f in all_files(self.path)
            if f.endswith('.met') and f.find('CompilerIdCXX')<0 and f.find('CompilerIdC')<0 and f.find('third_party')<0]
	#print "met files: %s"%(self.met_files)
        
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
	#print "\n\nhistogram"
	#print "metric: %s"%metric
	#print "numbins: %s"%numbins
	#print "minval: %s"%minval
        data = []
    	data_param_names = []
	data_param_filenames = []
	array = self.metrics[metric].data
	for d in array:
	    #filter
	    if ('/cpp' in d[5]) or  ('/srv_gen' in d[5]) or ('/msg_gen' in d[5]): continue
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


	# Sorting 'data_param_filenames' [min,...,max]
	keys = data
	values_fn = data_param_filenames
	tuple_sorted_fn = sorted(zip(keys, values_fn))
	tuple_values_fn = list()
	tuple_names_fn = list()
	for x in tuple_sorted_fn:
	    #if not '/cpp/' in x[1]: 
	    tuple_values_fn.append(x[0])
	    tuple_names_fn.append(x[1])		

	# Sorting 'data_param_names' [min,...,max]
	keys = data
	values_n = data_param_names
	tuple_sorted_n = sorted(zip(keys, values_n)) 
	tuple_names_n = list()
	for x in tuple_sorted_n:
	    tuple_names_n.append(x[1])		

	#print "length keys %s"%len(keys)
	#print "length values_fn %s"%len(values_fn)
	#print "length data %s"%len(data)
	#print "length tuple_names_n %s"%len(tuple_names_n)
	#print "length tuple_values_n %s"%len(tuple_values_n)
	#print "--------------------------\n\n\n"
	
	data_filenames = tuple_names_fn
	data_affected = tuple_names_n
	data_file_values = tuple_values_fn

        # Calculate average of metric	
    	metric_average = 0.0
    	counts_sum = 0.0
    	for i in range(len(data)):
            metric_average += float(data[i])
	    counts_sum += 1
    	metric_average /= counts_sum
    	metric_average = round(metric_average, 2)


	# Append data to histogram 
        m = self.metrics[metric]
        for i in range(len(hist)):
            m.histogram_counts.append(hist[i])
            m.histogram_labels.append(histogram_labels[i])

	for i in range(len(data_file_values)):
	    m.histogram_file_values.append(data_file_values[i])

	for i in range(len(data_affected)):
	    m.histogram_affected.append(data_affected[i])

	for i in range(len(data_filenames)):
	    m.histogram_filenames.append(data_filenames[i])

	m.metric_average.append(metric_average)

	# Append uri data to histogram
	m.uri.append(options.uri)
	m.uri_info.append(options.uri_info)
	m.vcs_type.append(options.vcs_type)
	m.datetime.append(strftime("%Y-%m-%d %H:%M:%S", gmtime()))


    def process_met_file(self, met_file):
        stack = self.get_stack(met_file)
        package = self.get_package(met_file)
        package_dir = self.get_package_dir(met_file)
        stack_dir = self.get_stack_dir(met_file)
        filename = ''
        name = ''   
        met = open(met_file,'r')
	#print "met in process_met_file: %s"%met_file
	#print "stack: %s"%stack
	#print "stack_dir: %s"%stack_dir
        while met: #cmd= metric_name | val= value
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
	        #print "cmd: %s"%cmd
	        #print "val: %s"%val
                if cmd == 'STFIL':
                    filename = val
                    continue
                if cmd == 'STNAM':
                    name = val
                    continue
                # filter out entries outside of the current stack
                if filename.find(options.path_src) < 0: continue
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

        #print "metric.data: %s"%metric.data
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
	    config['histogram_affected'] = [b for b in metric.histogram_affected] 
	    config['histogram_filenames'] = [b for b in metric.histogram_filenames] 
	    config['histogram_file_values'] = [b for b in metric.histogram_file_values] 
	    config['metric_average'] = [b for b in metric.metric_average] 
	    config['uri'] = [b for b in metric.uri]  
	    config['uri_info'] = [b for b in metric.uri_info]  
	    config['vcs_type'] = [b for b in metric.vcs_type]
	    config['datetime'] = [b for b in metric.datetime] 
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
        #print "os.environ['WORKSPACE']: %s"%(os.environ['WORKSPACE'])
	helper = subprocess.Popen(('%s/jenkins_scripts/code_quality/cloc.pl %s --not-match-d=%s/build --yaml --out %s'%(os.environ['WORKSPACE'],self.path_src, self.path_src, filename)).split(' '),env=os.environ)
        helper.communicate()
                      
    def export(self):
        # process all met files
        for met in self.met_files:
            #print "met: %s"%met
            self.process_met_file(met)
            
        # create histograms
	for m in self.config['metrics'].keys():
	    #print "\n\nm: %s"%m
            if not m in self.metrics:
                continue
	    #print "\nCALL HISTOGRAMM"
            config = self.config['metrics'][m]
	    self.histogram(m, config['histogram_num_bins'], config['histogram_minval'], config['histogram_maxval'], config['data_type'])

        # create yaml
        self.create_code_quality_yaml()
        
        # create csv
        self.create_csv()
        self.create_csv_hist()
        
        # export code lines of code
        self.create_loc()


def _load_code_quality_file(filename, name, type_='package'):
    """
    Load code_quality.yaml properties into dictionary for package
    @param filename: file to load code_quality data from
    @param name: printable name (for debugging)
    @return: code_quality properties dictionary
    @raise UtilException: if unable to load. Text of error message is human-readable
    """
    print 'filename: %s'%filename
    if not os.path.exists(filename):
        raise UtilException('Newly proposed, mistyped, or obsolete %s. Could not find %s "'%(type_, type_) + name + '" in rosdoc')

    try:
        #filename = "/var/www/www.ros.org/html/doc/navigation/code_quality.yaml"
        with open(filename) as f:
            data = yaml.load(f)
    except yaml.YAMLError, exc:
        raise UtilException("Error loading code quality data: %s %s"%(filename,repr(exc)))

    if not data:
        raise UtilException("Unable to retrieve code quality data. Auto-generated documentation may need to regenerate")
    return data

def stack_code_quality_file(stack):
    """
    Generate filesystem path to code_quality.yaml for stack
    """
    return os.path.join(options.doc, stack, "code_quality.yaml")

def load_stack_code_quality(stack_name, lang=None):
    """
    Load code_quality.yaml properties into dictionary for package
    @param lang: optional language argument for localization, e.g. 'ja'
    @return: stack code quality properties dictionary
    @raise UtilException: if unable to load. Text of error message is human-readable
    """
    data = _load_code_quality_file(stack_code_quality_file(stack_name), stack_name, 'stack')
    return data

def update_distro_yaml(file_path, stack, new_average):
    with open(file_path, 'r') as f:
        distro_file = yaml.load(f)

    #if stack in distro_file:
     #   distro_file[stack] = new_average
     #   print 'gotcha'
    #else:
    #    distro_file[stack] = new_average
    distro_file[stack] = new_average
    
    with codecs.open(file_path, mode='w', encoding='utf-8') as f:
        f.write(yaml.safe_dump(distro_file, default_style="'")) 


        
if __name__ == '__main__':   
    (options, args) = get_options(['path', 'path_src', 'config', 'distro', 'stack', 'uri', 'uri_info', 'vcs_type'], ['doc','csv'])
    if not options:
        exit(-1)
    
    with open(options.config) as f:
        config = yaml.load(f)
    
    # get meta-packages  
    print 'Exporting meta-packages to yaml/csv'      
    stack_files = [f for f in all_files(options.path) if f.endswith('CMakeCache.txt')] #TODO: adjust var name's -> meta-package
    stack_dirs = [os.path.dirname(f) for f in stack_files]
    for stack_dir in stack_dirs:
	# build path
        stack = (options.stack).strip('[]').strip("''") #os.path.basename(stack_dir)
        doc_dir = options.doc + '/' + stack
        csv_dir = options.csv + '/' + stack
	#print "stack_dir: %s"%(stack_dir)
	#print "stack: %s"%(stack)
	#print "doc_dir: %s"%(doc_dir)
	#print "csv_dir: %s"%(csv_dir)
	# export
        hh = ExportYAML(config, stack_dir, options.path_src, doc_dir, csv_dir, options.distro, options.stack, options.uri, options.uri_info, options.vcs_type)
        hh.export()
	
    # get packages  
    print 'Exporting packages to yaml/csv'  
    stack_files = [f for f in all_files(options.path_src) if f.endswith('package.xml')]
    stack_dirs = [os.path.dirname(f) for f in stack_files]
    for stack_dir in stack_dirs:
	# build path
        stack = os.path.basename(stack_dir)
        doc_dir = options.doc + '/' + stack
        csv_dir = options.csv + '/' + stack
	package_dir = options.path + '/' + stack
	package_dir_src = options.path_src + '/' + stack
	# export
        hh = ExportYAML(config, package_dir, options.path_src, doc_dir, csv_dir, options.distro, options.stack, options.uri, options.uri_info, options.vcs_type)
        hh.export()
        
        
        
    # load distro yaml
    lang = None
    collect_averages = dict()
    data = load_stack_code_quality(options.stack, lang)
    # collect all average values of metrics
    for m in data.keys():
        collect_averages[m] = data[m].get('metric_average', '')
    # pull distro yaml
    origin = ROS_WIKI_SERVER + '/' + '%s.yaml'%options.distro 
    destination= options.doc
    call('sudo scp -oStrictHostKeyChecking=no -r %s %s' % (origin, destination),os.environ, 'Pull rosdistro yaml')
    # update distro yaml
    file_path = destination + '/' + '%s.yaml'%options.distro 
    update_distro_yaml(file_path, options.stack, collect_averages)
    # push distro yaml
    origin = options.doc + '/%s.yaml'%options.distro
    call('sudo scp -oStrictHostKeyChecking=no %s %s' % (origin, ROS_WIKI_SERVER),os.environ, 'Push distro-yaml-file to ros-wiki ')
