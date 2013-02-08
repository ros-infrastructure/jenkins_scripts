#!/usr/bin/env python
import sys
import os
import shutil
from glob import iglob
import optparse 

def get_options(required, optional):
    parser = optparse.OptionParser()
    ops = required + optional
    if 'dir' in ops:
        parser.add_option('--dir', dest = 'dir', default='.', action='store',
                          help='dir to scan')
    if 'filelist' in ops:
        parser.add_option('--filelist', dest = 'filelist', default='filelist.list', action='store',
                          help='output filelist file')
                          
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
            #yield os.path.join(path, f)

            
def main():
    # parse command line options
    (options, args) = get_options([], ['dir', 'filelist'])
    if not options:
        return -1
                
    source_files = [f for f in all_files(options.dir)
                   if f.endswith('filelist.lst') and f.find('CompilerIdCXX')<0 and f.find('CompilerIdC')<0]

    # create a file to write
    filename = options.filelist
    f = open(filename,"w")

    for name in source_files:
        shutil.copyfileobj(open(name,'rb'), f)
        
    f.close()
    
    return 0

if __name__ == '__main__':
    try:
        res = main()
        sys.exit(res)
    except Exception, ex:
        print ex
        sys.exit(-1)
        
