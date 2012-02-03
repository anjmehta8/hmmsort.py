#!/bin/env python2.6

"""
Functions to post-process the output from the hmm_sorting matlab routines
"""


import numpy as np
import h5py
import os
import sys
import pylab as plt
import glob
import h5py
from PyNpt import fileWriters as fw
from mpl_toolkits.axisartist import Subplot
import scipy.cluster.hierarchy as hcluster
import scipy.weave as weave

def formatAxis(ax):
    try:
        ax.axis['bottom'].major_ticks.set_tick_out(True)
        ax.axis['bottom'].minor_ticks.set_tick_out(True)
        ax.axis['left'].major_ticks.set_tick_out(True)
        ax.axis['left'].minor_ticks.set_tick_out(True)
    except:
        pass
    ax.axis['right'].set_visible(False)
    ax.axis['top'].set_visible(False)

def writeWwaveformsFile(data,samplingRate=29990):

    timestamps = ((np.concatenate(data['unitTimePoints'].values(),axis=0))/(samplingRate/1000.0)).astype(np.uint64)
    fw.writeWaveformsFile(data['allSpikes'].transpose((0,2,1)),timestamps,'testwaveforms.bin')
    #get the 
    cids = np.concatenate([np.array([[k]*len(v),v]) for k,v in data['spikeIdx'].items()],axis=1)
    cids.astype(np.uint64).tofile('testwaveforms.overlap')
    ucids = cids.copy()
    C = np.bincount(cids[1,:])
    ucids[0,C[C>1]] = -1
    ucids[0,:].tofile('testwaveforms.cut',sep='\n')



def processFiles(pattern,outfile=None): 
    """
    Pattern could be any file pattern that glob understands.
    """
    files = glob.glob(pattern)
    #get numeric part of file names
    P = pattern.replace('*','([0-9]*)')
    F = ' '.join((files))
    nparts = glob.re.findall(P,F)
    ndigits = len(nparts[0])
    nparts = np.array(map(int,nparts))
    #sort
    fidx = np.argsort(nparts)
    #detect any gaps
    gaps = np.diff(nparts[fidx])
    gapidx = np.where(gaps>1)[0]
    gaps = gaps[gapidx]
    if len(gaps) > 0:
        mf = np.concatenate([nparts[fidx][gapidx[i]] + np.arange(1,gaps[i]) for i in xrange(len(gaps))])
        ps = pattern.replace('*','%.4d')
        print "Gaps detected. The missing files are most likely:"
        for q in mf:
            print ps % q
        query = raw_input('Accept [y/n]')
        if query == 'n':
            return {}

    data = {'dataSize':0}
    spIdxOffset = 0
    for fi in xrange(len(files)):
        f = files[fidx[fi]]
        print "Processing file %s" % (f,)
        sys.stdout.flush()
        datafile = f.replace('.mat','') 
        qdata = processData(f,datafile)
        for k in qdata.keys():
            if isinstance(qdata[k],dict):
                if not k in data:
                   data[k]  = {}
                for kk,vv in qdata[k].items():
                    if not kk in data[k]:
                        #data[ks][kks] = np.empty((0,)+vv.shape[1:])
                        data[k][kk] = vv
                    else:
                        if k == 'unitTimePoints':
                            data[k][kk] = np.concatenate((data[k][kk],vv+data['dataSize']),axis=0)
                        elif k == 'spikeIdx':
                            data[k][kk] = np.concatenate((data[k][kk],vv+spIdxOffset),axis=0)
                        elif k == 'uniqueIdx' or k == 'nonOverlapIdx':
                            data[k][kk] = np.concatenate((data[k][kk],vv+data[k][kk].shape[0]),axis=0)
                        else:
                            data[k][kk] = np.concatenate((data[k][kk],vv),axis=0)
            else:
                if k == 'dataSize':
                    if fidx[fi] in gapidx:
                        #we have a gap; i.e. the next file is missing. In that
                        #case, we have to offset by more
                        data[k]+=gaps[gapidx==fidx[fi]]*qdata[k]
                    else:
                        data[k]+=qdata[k]
                else:
                    if not k in data:
                        data[k] = np.empty((0,)+qdata[k].shape[1:])
                    data[k] = np.concatenate((data[k],qdata[k]),axis=0)
        spIdxOffset += qdata['allSpikes'].shape[0]

    return data

def processFilesHDF5(pattern,outfile=None): 
    files = glob.glob(pattern)
    if outfile == None:
        base,pt,ext = pattern.partition('.')
        base.replace('*','')
        outfile  = '.'.join((base,'hdf5'))
        outfile = os.path.expanduser('~/Documents/research/data/%s' % outfile)
    data = h5py.File(outfile,'w')
    try:
        data['dataSize'] = np.array([0]) 
        spIdxOffset = 0
        for f in files:
            datafile = f.replace('.mat','') 
            qdata = processData(f,datafile)
            for k in qdata.keys():
                ks = str(k)
                if isinstance(qdata[k],dict):
                    if not ks in data:
                        g = data.create_group(ks)
                    for kk,vv in qdata[k].items():
                        kks = str(kk)
                        if not kks in data[ks]:
                            #data[ks][kks] = np.empty((0,)+vv.shape[1:])
                            data[ks][kks] = vv
                        else:
                            if k == 'unitTimePoints':
                                data[ks][kks] = np.concatenate((data[ks][kks],vv+data['dataSize']),axis=0)
                            elif k == 'spikeIdx':
                                data[ks][kks] = np.concatenate((data[ks][kks],vv+spIdxOffset),axis=0)
                            else:
                                data[ks][kks] = np.concatenate((data[ks][kks],vv),axis=0)
                else:
                    if k == 'dataSize':
                        data[ks]+=qdata[k]
                    else:
                        if not ks in data:
                            data[ks] = np.empty((0,)+qdata[k].shape[1:])
                        data[ks] = np.concatenate((data[ks],qdata[k]),axis=0)
            spIdxOffset += qdata['allSpikes'].shape[0]
            data.flush()
    finally:
        data.close()

    data = h5py.File(outfile,'r')
    return data

def processData(fname,dataFile=None):

    if not os.path.isfile(fname):
        print "Sorry, the file %s could not be found" % fname
        return
    try:
        sortData = h5py.File(fname,'r')
        
        #load the state sequence for all neurons
        seq = sortData['mlseq'][:].astype(np.int).T
        #load the spike forms for each neuron
        spikeForms = sortData['spikeForms'][:].transpose((2,1,0))
        
        #create a signal with overlaps on each channel
        #S = spikeForms[np.arange(spikeForms.shape[0])[:,None,None],np.arange(spikeForms.shape[1])[None,:,None],seq[:,None,:]].sum(0)
        #find where at least one neuron is active
        idx = np.where((seq>0).any(0))[0]

        noverlapPts = spikeForms.shape[0]*spikeForms.shape[-1]
        #find the total number of states (including overlaps) involved in each
        #spike
        pidx = np.append([0],np.append(np.where(np.diff(idx)>1)[0]+1,[len(idx)]))
        cidx =np.diff(pidx)
        #get the start and the end points of each compound spike
        spikeStart = np.where((seq==1).any(0)*(seq<=1).all(0))[0]
        #make sure to exclude spikes that start towards the end of the
        #file;these will not have an ending point
        spikeStart = spikeStart[spikeStart<seq.shape[1]-spikeForms.shape[-1]]
        spikeEnd = np.where((seq==spikeForms.shape[-1]-1).any(0)*((seq==spikeForms.shape[-1]-1)+(seq==0)).all(0))[0]
        pidx = np.array([spikeStart,spikeEnd]).T.flatten()
        #create a spike matrix
        spMatrix = np.zeros((len(cidx),spikeForms.shape[1],noverlapPts)).transpose((1,0,2))
        spIdxMatrix = np.zeros((len(cidx),noverlapPts),dtype=np.int)

        #create an index that will place each overlap spike in the correct position
        #in the spike matrix
        k,l = np.where(np.arange(noverlapPts)[None,:]<cidx[:,None])

        #k and l now gives the spike index and the timepoint index into the spMatrix
        #spMatrix[:,k,l] = S[:,idx]
        #TODO: we should extact the spikes here, i.e. use the +/- 3pt refractory
        #period around each spikes
        #spIdxMatrix[k,l] = idx.astype(np.int)
        #spMatrix = spMatrix.transpose((1,0,2))
        #find the minimum point on each channel and shift each spike such that the
        #minimum point occurs at 1/3
        #spidx = spMatrix.min(1).argmin(1)
        #tpts = int(1/3.0*spikeForms.shape[-1])
        #W = np.array([np.roll(spMatrix[u],tpts-spidx[u],axis=-1) for u in xrange(len(spidx))])
       
        #create a dictionary of spike indices assigned to each unit
        minpts = spikeForms.min(1).argmin(1)
        #get the index of each minimum point for each neuron
        i,j = np.where(seq==minpts[:,None])
        i = i[j<seq.shape[1]-22]
        j = j[j<seq.shape[1]-22]
        #find the true overlaps, i.e. spikes that differ by less than 3 points
        """
        d = j[:,None]-j
        k,l = ((d<=3)*(d>0))
        """
        #tids = hcluster.fclusterdata(j[:,None],3,criterion='distance',metric='cityblock')-1
        #get an index into the original timestamp array for the unique points
        #u,q = np.unique(tids)
        #find wich compound spike each single unit spike contributes to
        #cspike,spidx = np.where(((j[:,None] >= spikeStart)*(j[:,None] <= spikeEnd)))
        #cspikes,spidx,uspidx = np.unique(spidx,return_index=True,return_inverse=True)
        #qidx = np.digitize(j,pidx)
        units = dict([(u,j[i==u]) for u in np.unique(i)]) 
        #spikeIdx = dict([(u,spidx[uspidx[i==u]]) for u in np.unique(i)]) 
        spikeIdx = dict([(u,np.where(i==u)[0]) for u in np.unique(i)]) 
        spikes = {}
        channels = None
        if 'data' in sortData:
            data = sortData['data'][:]
        elif dataFile != None:
            fid = open(dataFile,'r')
            hs = np.fromfile(fid,dtype=np.uint32,count=1)
            nchs = np.fromfile(fid,dtype=np.uint8,count=1).astype(np.int64)
            fid.close()
            data = np.memmap(dataFile,dtype=np.int16,offset=hs,mode='r')
            data = data.reshape(data.size/nchs,nchs)
            if 'Channels' in sortData:
                channels = sortData['Channels'][:].flatten().astype(np.int)-1
                data = data[:,channels]
        else:
            print "Sorry, no data found. Exiting..."
            sortData.close()
            return {'unitTimePoints': units,'spikeIdx':spikeIdx}
        
        keys = np.array(units.keys())
        uniqueIdx = {}
        nonoverlapIdx = {}
        for c in keys: 
            idx = units[c]
            idx = idx[idx<data.shape[0]-22][:,None]+ np.arange(-10,22)[None,:]
            spikes[c] = data[idx,:]
            otherkeys = keys[keys!=c] 
            uniqueIdx[c] = np.where(np.array([pdist_threshold(units[c],units[c1],3) for c1 in otherkeys]).prod(0))[0]
            nonoverlapIdx[c] = np.where(np.array([pdist_threshold(units[c],units[c1],32) for c1 in otherkeys]).prod(0))[0]

        #get the unique spikes
        allSpikeIdx = np.concatenate(units.values(),axis=0)
        allSpikeIdx = (allSpikeIdx[allSpikeIdx<data.shape[0]-22][:,None]+np.arange(-10,22))[:,None,:].repeat(data.shape[1],1)
        allSpikes = data[allSpikeIdx,np.arange(data.shape[1])[None,:,None]].transpose((0,2,1))
        dataSize = data.shape[0]
        del data

    finally:
        sortData.close()
    
    
    return {'unitTimePoints': units,'unitSpikes':spikes,'allSpikes':allSpikes,'spikeIdx':spikeIdx,'dataSize':dataSize,'spikeForms':spikeForms,'channels':channels,'uniqueIdx':uniqueIdx,'nonOverlapIdx': nonoverlapIdx}

def pdist_threshold(a1,a2,thresh):
    n1 = len(a1)
    n2 = len(a2)
    idx = np.ones((n1,),dtype=np.uint8)
    code = """
    unsigned int i,j;
    double d;
    for(i=0;i<n1;i++)
    {
        for(j=0;j<n2;j++)
        {
            d = a1[i]-a2[j];
            d = sqrt(d*d);
            if( d < thresh )
            {
                idx[i] = 0;
                break;
            }
        }
    }
    """
    err = weave.inline(code,['a1','a2','n1','n2','thresh','idx'])

    return idx.astype(np.bool)

def pdist_threshold2(a1,a2,thresh):
    n1 = len(a1)
    n2 = len(a2)
    idx = np.ones((n1,),dtype=np.uint8)
    code1 = """
    unsigned int i,j,c;
    double d;
    c = 0;
    //first pass; count the number of items
    for(i=0;i<n1;i++)
    {
        for(j=0;j<n2;j++)
        {
            d = a1[i]-a2[j];
            d = sqrt(d*d);
            if( d < thresh )
            {
                c+=1;
            }
        }
    }
    return_val = c;
    """
    c = weave.inline(code1,['a1','a2','n1','n2','thresh'])
    print c 
    dist = np.zeros((c,))
    code = """
    unsigned int i,j,k;
    double d;
    k = 0;
    for(i=0;i<n1;i++)
    {
        for(j=0;j<n2;j++)
        {
            d = a1[i]-a2[j];
            if( sqrt(d*d) < thresh )
            {
                dist[k] = d;
                k++;
            }

        }
    }
    """
    err = weave.inline(code,['a1','a2','n1','n2','thresh','dist'])

    return dist 

def plotSpikes(qdata,save=False,fname='hmmSorting.pdf'):

    allSpikes = qdata['allSpikes'] 
    unitSpikes = qdata['unitSpikes']
    spikeIdx = qdata['spikeIdx']
    spikeIdx = qdata['unitTimePoints']
    units = qdata['unitTimePoints']
    spikeForms = qdata['spikeForms']
    channels = qdata['channels']
    uniqueIdx = qdata['uniqueIdx']
    samplingRate = qdata.get('samplingRate',30000.0)
    """
    mustClose = False
    if isinstance(dataFile,str):
        dataFile = h5py.File(dataFile,'r')
        mustClose = True
    data = dataFile['data'][:]
    """
    keys = np.array(units.keys())
    x = np.arange(32)[None,:] + 42*np.arange(4)[:,None]
    xt = np.linspace(0,31,spikeForms.shape[-1])[None,:] + 42*np.arange(4)[:,None]
    xch = 10 + 42*np.arange(4)
    for c in units.keys():
        ymin,ymax = (5000,-5000)
        fig = plt.figure(figsize=(10,6))
        print "Unit: %d " %(c,)
        print "\t Plotting waveforms..."
        sys.stdout.flush()
        #allspikes = data[units[c][:,None]+np.arange(-10,22)[None,:],:]
        #allspikes = allSpikes[spikeIdx[c]]
        allspikes = qdata['unitSpikes'][c]
        otherunits = keys[keys!=c]
        #nonOverlapIdx = np.prod(np.array([~np.lib.arraysetops.in1d(spikeIdx[c],spikeIdx[c1]) for c1 in otherunits]),axis=0).astype(np.bool)
        #nonOverlapIdx = np.prod(np.array([pdist_threshold(spikeIdx[c],spikeIdx[c1],3) for c1 in otherunits]),axis=0).astype(np.bool)
        #nonOverlapIdx = uniqueIdx[c]
        nonOverlapIdx = qdata['nonOverlapIdx'][c]
        overlapIdx = np.lib.arraysetops.setdiff1d(np.arange(qdata['unitTimePoints'][c].shape[0]),nonOverlapIdx)
        #allspikes = allSpikes[np.lib.arraysetops.union1d(nonOverlapIdx,overlapIdx)]
        ax = Subplot(fig,2,3,1)
        fig.add_axes(ax)
        formatAxis(ax)
        #plt.plot(x.T,sp,'b')
        m = allspikes.mean(0)
        s = allspikes.std(0)
        plt.plot(x.T,m,'k',lw=1.5)

        plt.plot(xt.T,spikeForms[c].T,'r')
        for i in xrange(x.shape[0]):
            plt.fill_between(x[i],m[:,i]-s[:,i],m[:,i]+s[:,i],color='b',alpha=0.5)
        yl = ax.get_ylim()
        ymin = min(ymin,yl[0])
        ymax = max(ymax,yl[1])
        ax.set_title('All spikes (%d)' % (allspikes.shape[0],))

        ax = Subplot(fig,2,3,2)
        fig.add_axes(ax)
        formatAxis(ax)
        m =  allspikes[nonOverlapIdx,:,:].mean(0)
        s =  allspikes[nonOverlapIdx,:,:].std(0)
        plt.plot(x.T,m,'k',lw=1.5)
        plt.plot(xt.T,spikeForms[c].T,'r')
        for i in xrange(x.shape[0]):
            plt.fill_between(x[i],m[:,i]-s[:,i],m[:,i]+s[:,i],color='b',alpha=0.5)
        yl = ax.get_ylim()
        ymin = min(ymin,yl[0])
        ymax = max(ymax,yl[1])
        #for sp in allspikes[nonOverlapIdx,:,:]:
        #    plt.plot(x.T,sp,'r')

        ax.set_title('Non-overlap spikes (%d)' %(nonOverlapIdx.shape[0],))
        ax = Subplot(fig,2,3,3)
        fig.add_axes(ax)
        formatAxis(ax)

        m =  allspikes[overlapIdx,:,:].mean(0)
        s =  allspikes[overlapIdx,:,:].std(0)
        plt.plot(x.T,m,'k',lw=1.5)
        plt.plot(xt.T,spikeForms[c].T,'r')
        for i in xrange(x.shape[0]):
            plt.fill_between(x[i],m[:,i]-s[:,i],m[:,i]+s[:,i],color='b',alpha=0.5)
        yl = ax.get_ylim()
        ymin = min(ymin,yl[0])
        ymax = max(ymax,yl[1])
        #for sp in allspikes[~nonOverlapIdx,:,:]:
        #    plt.plot(x.T,sp,'g')
        ax.set_title('Overlap spikes (%d)' % ((overlapIdx).shape[0],))
        for a in fig.axes:
            a.set_ylim((ymin,ymax))
            a.set_xticks(xch)
            a.set_xticklabels(map(str,channels))
            a.set_xlabel('Channels')
        for a in fig.axes[1:]:
            a.set_yticklabels([])
        fig.axes[0].set_ylabel('Amplitude')
        """
        isi distribution
        """
        print "\t ISI distribution..."
        sys.stdout.flush()
        timepoints = qdata['unitTimePoints'][c]/(samplingRate/1000)
        isi = np.log(np.diff(timepoints))
        n,b = np.histogram(isi,100)
        ax = Subplot(fig,2,3,4)
        fig.add_axes(ax)
        formatAxis(ax)
        ax.plot(b[:-1],n,'k')
        yl = ax.get_ylim()
        ax.vlines(0.0,0,yl[1],'r',lw=1.5)
        ax.set_xlabel('ISI [ms]')
        #get xticklabels
        xl,xh = int(np.round((b[0]-0.5)*2))/2,int(np.round((b[-1]+0.5)*2))/2
        xl = -0.5
        dx = np.round((xh-xl)/5.0)
        xt_ = np.arange(xl,xh+1,dx)
        ax.set_xticks(xt_)
        ax.set_xticklabels(map(lambda s: r'$10^{%.1f}$' % (s,),xt_))

        """
        auto-correlogram
        """
        print "\t auto-correllogram..."
        sys.stdout.flush()
        if not 'autoCorr' in qdata:
            qdata['autoCorr'] = {}
        if not c in qdata['autoCorr']:
            C = pdist_threshold2(timepoints,timepoints,50)
            qdata['autoCorr'][c] = C
        else:
            C = qdata['autoCorr'][c]
        n,b = np.histogram(C[C!=0],np.arange(-50,50))
        ax = Subplot(fig,2,3,5)
        fig.add_axes(ax)
        formatAxis(ax)
        ax.plot(b[:-1],n,'k')
        ax.fill_betweenx([0,n.max()],-1.0,1.0,color='r',alpha=0.3)
        ax.set_xlabel('Lag [ms]')
        if save:
            fn = os.path.expanduser('~/Documents/research/figures/SpikeSorting/hmm/%s' % (fname.replace('.pdf','Unit%d.pdf' %(c,)),))
            fig.savefig(fn,bbox='tight')

    if not save:
        plt.draw()
    """
    if mustClose:
        dataFile.close()
    """


def plotXcorr(qdata,save=False,fname='hmmSortingUnits.pdf'):

    unitTimePoints = qdata['unitTimePoints']
    samplingRate = qdata.get('samplingRate',30000.0)
    fig = plt.figure(figsize=(10,10) )
    units = unitTimePoints.keys()
    nunits = len(units)
    i = 1
    if not 'XCorr' in qdata:
        qdata['XCorr'] = {}
    for k1 in xrange(len(units)-1) :
        if not k1 in qdata['XCorr']:
            qdata['XCorr'][k1] = {}
        for k2 in xrange(k1+1,len(units)):
            if not k2 in qdata['XCorr'][k1]:
                T1 = unitTimePoints[k1]/(samplingRate/1000)
                T2 = unitTimePoints[k2]/(samplingRate/1000)
                #compute differences less than 50 ms
                C = pdist_threshold2(T1,T2,50)
                qdata['XCorr'][k1][k2] = C
            else:
                C = qdata['XCorr'][k1][k2]
            n,b = np.histogram(C,np.arange(-50,50))
            ax = Subplot(fig,nunits-1,nunits,k1*nunits+k2) 
            fig.add_axes(ax)
            formatAxis(ax)
            ax.plot(b[:-1],n,'k')
            ax.fill_betweenx([0,n.max()],-1.0,1.0,color='r',alpha=0.3)
    if save:
        pass
    else:
        plt.draw()