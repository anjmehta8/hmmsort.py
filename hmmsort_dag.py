import sys
import os
import glob

levels = ['day','session','array','channel']

def level(cwd):
     pp = cwd.split(os.sep)[-1]
     ll = ''
     if pp.isdigit():
         ll = 'day'
     else:
         ll = pp.strip(''.join([str(i) for i in xrange(10)]))
     return ll
        

if __name__ == '__main__':
    if len(sys.argv) == 1:
        print "Usage: hmmsort_dag.py <execroot>"
        sys.exit(0)
    execroot = sys.argv[1]
    thislevel = level(os.getcwd())
    # get all highpass datafiles
    levelidx = levels.index(thislevel)
    if levelidx == len(levels)-1:
        bb = "." 
        ch = 1
    else:
        # construct a pattern for finding all highpass files below this level
        bb = os.sep.join([levels[i]+"*" for i in xrange(levelidx+1,len(levels))])
        ch = None
    bb = os.sep.join([bb] + ["*highpass.mat"])
    files = glob.glob(bb)
    
    with open("hmmsort.dag","w") as fid:
        for f in files:
            pp = f.split(os.sep)  # get the channel
            fn = pp[-1]
            dd = os.sep.join(pp[:-1])
            # make sure that the output dir exists
            outdir = os.path.isdir(os.sep.join(dd, "hmmsort"))
            if not os.path.isdir(outdir):
                os.mkdir(outdir)
            if ch is None:
                ch = int(filter(str.isdigit, pp[-2]))
            fid.write('JOB hmmlearn_%d %s/hmmsort.cmd DIR %s\n' % (ch, execroot,dd))
            fid.write('VARS hmmlearn_%d fname="%s"\n' %(ch, fn))
            fid.write('VARS hmmlearn_%d execroot="%s"\n' %(ch, execroot))
            fid.write('JOB hmmdecode_%d %s/hmmdecode.cmd DIR %s\n' % (ch, execroot, dd))
            fid.write('VARS hmmdecode_%d fname="%s"\n' %(ch, fn))
            fid.write('VARS hmmdecode_%d outfile="hmmsort/spike_templates.hdf5"\n' %(ch, ))
            fid.write('VARS hmmdecode_%d execroot="%s"\n' %(ch, execroot))
            fid.write('PARENT hmmlearn_%d CHILD hmmdecode_%d\n' % (ch, ch))
            fid.write('\n')

