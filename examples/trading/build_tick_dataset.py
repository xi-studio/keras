import os
import glob
import time
import datetime
import ctypes
import numpy as np
import math
import gzip
import cPickle
import pylab as plt
import matplotlib.gridspec as gridspec
from profilehooks import profile
import csv

from ifshort_rnn import build_rnn, build_mlp, train

#from ordereddict import OrderedDict
OrderedDict = dict

from preprocessor2 import *
            
base_dir = '/home/xd/data/trading'

def get_day_dir(exchange, year, month, day):
    assert year == 2015
    if year == 2015: 
        return '%s/f_c%d/f_c%d%02dd/%s/%d%02d%02d' % (base_dir, year, year, month, exchange, year, month, day)
    else:
        return None
        
def find_main_contract_path(day_dir, commodity):
    max_size = 0
    main_contract_path = ''
    for contract_path in glob.glob('%s/%s*' % (day_dir, commodity)):
        size = os.path.getsize(contract_path)
        if size > max_size:
            main_contract_path = contract_path
            max_size = size
#    print main_contract_path, max_size
    return main_contract_path

def get_paths(exchange, commodity, year, months):
    paths = []       
    for month in months:     
        for day in range(1, 32):
            day_dir = get_day_dir(exchange, year, month, day)
#            print day_dir
            if os.path.isdir(day_dir):
                mc_path = find_main_contract_path(day_dir, commodity)
                paths.append(mc_path)
    return paths
            
def load_ticks(exchange, commodity, year, months, use_cache=True):
    fname = '%s/ticks_%s%d%02d.pkl' % (base_dir, commodity, year % 1000, months[0])
    if use_cache and os.path.isfile(fname):
        ticks = OrderedDict()
        for month in months:
            fname = '%s/ticks_%s%d%02d.pkl' % (base_dir, commodity, year % 1000, month)
            print 'Loading', fname
            with open(fname) as f:
                dict_stack(ticks, cPickle.load(f))
        return ticks
        
    paths = get_paths(exchange, commodity, year, months)
    ticks = OrderedDict()
    for path in paths:
        with open(path) as f:
            reader = csv.reader(f)
            prev = None
            prev_tick = None
            n_ticks = 0
            reader.next()
            for data in reader:
                now = datetime.datetime.strptime(data[2], '%Y-%m-%d %H:%M:%S.%f')
                if prev is None and not (now.time().minute == 0 and now.time().second in [0, 1]):
                    continue
                if now.time().hour == 15 and (now.time().minute > 0 or now.time().second > 0):
                    break
                if 0 < now.time().microsecond < 500000:
                    now = now.replace(microsecond=0)
                if 500000 < now.time().microsecond < 1000000:
                    now = now.replace(microsecond=500000) 
                tick = make_tick2(data)
                if prev is not None:
                    if now < prev:
                        continue
                    if now == prev:
                        if prev.time().microsecond == 0:
                            now = now + datetime.timedelta(microseconds=500000)
                        else:
                            assert prev.time().microsecond == 500000
                            continue
                    dt = now - prev
                    if dt.microseconds not in [0, 500000]:
                        print now, 'dt.microseconds =', dt.microseconds
                        break
                    
                    if dt.seconds >= 60 * 14:
                        n_missed = ((dt.seconds % (60 * 15))* 1000000 + dt.microseconds) / 500000
                        n_missed = 0
                    else:
                        n_missed = (dt.seconds * 1000000 + dt.microseconds) / 500000 - 1
                    if n_missed > 100:
                        print now, 'n_missed =', n_missed, 'dt.seconds =', dt.seconds
                    for _ in range(n_missed):
                        dict_append(ticks, prev_tick)
                        n_ticks += 1
                if tick['ask_price'] == 0 or tick['bid_price'] == 0:
                    print now, 'ask_price =', tick['ask_price'], 'bid_price =', tick['bid_price'], tick['ask_vol'], tick['bid_vol']
                    if not tick['last_price'] > 0:
                        print 'last_price =', tick['last_price']
                        assert False
                    if tick['ask_price'] == 0:
                        tick['ask_price'] = tick['last_price']
                    if tick['bid_price'] == 0:
                        tick['bid_price'] = tick['last_price']
                tick['price'] = (tick['ask_price'] + tick['bid_price']) * 1. / 2
                if tick['ask_vol'] == 0:
                    tick['ask_vol'] = tick['bid_vol']
                if tick['bid_vol'] == 0:
                    tick['bid_vol'] = tick['ask_vol']
                tick['time_in_ticks'] = n_ticks
                dict_append(ticks, tick)
                n_ticks += 1
                prev = now
                prev_tick = tick
            print path, n_ticks
    return as_arrays(ticks)

def make_tick2(data):
    t = {}
    d = data  
    t['last_price'] = int(float(d[3]))
    t['pos'] = int(d[4])
    t['pos_inc'] = int(d[5])
    t['vol'] = int(float(d[7]))
    t['open_vol'] = int(d[8])
    t['close_vol'] = int(d[9])
    assert d[11] in ['B', 'S']
    t['direction'] = 1 if d[11] == 'B' else -1
    
    t['ask_price'] = int(round(float(d[-3])))
    t['bid_price'] = int(round(float(d[-4])))
    t['ask_vol'] = int(d[-1])
    t['bid_vol'] = int(d[-2])
#    t['price'] = (float(d[-3]) + float(d[-4])) * 1. / 2
    return t
                      
def make_tick(data):
    t = {}
    d = data  
    t['ask_price'] = d[2]
    t['bid_price'] = d[18]
    t['price'] = (t['ask_price'] + t['bid_price']) * 1. / 2
    t['vol'] = sum(d[41:41+7])
    
    t['ask_vol'] = d[10]
    t['bid_vol'] = d[26]
    return t

#@profile
def as_arrays(X):
    for k in X:
        X[k] = np.array(X[k])
    return X

#@profile
def dict_append(X, x):
    if len(X) == 0:
        for key in x:
            X[key] = []
    for key in x:
        X[key].append(x[key])
  
def dict_stack(X, Y):
    if len(X) == 0:
        for key in Y:
            X[key] = np.array([])
    for key in Y:
        X[key] = np.append(X[key], Y[key])
              
def callback(context, data, len, score, latest_score):
    global ticks
    tick = make_tick(data)
    dict_append(ticks, tick)
#    now += 1
    game.Play(context, 1)
   
#if __name__ == "__main__":
##    for exchange, commodity in [('zc', 'SR'), ('zc', 'MA'), ('zc', 'TA'), ('dc', 'l'), ('dc', 'pp'), ('sc', 'ru')]:
#    for exchange, commodity in [('zc', 'SR')]:
#        year = 2015  
#        for month in range(1, 10):  
#            ticks = load_ticks(exchange, commodity, year, [month], use_cache=False)
#            fname = '%s/ticks_%s%d%02d.pkl' % (base_dir, commodity, year % 1000, month)
#            print 'Saving', fname, '...'
#            with open(fname, 'w') as f:
#                cPickle.dump(ticks, f)
       

#game = ctypes.CDLL("game.so")
#CMPFUNC = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int, ctypes.c_int) 
#_callback = CMPFUNC(callback)
#context = game.CreateContext('cfg_test.xml')
#game.RegisterCallback(context, _callback)
#print 'Running game...'
#ticks = OrderedDict()
#while not game.IsFinish(context):
#    game.RunOne(context)
#ticks = as_arrays(ticks)

ticks = load_ticks('zc', 'SR', 2015, range(1, 10), use_cache=True)

print 'Initializing preprocessor...'
pp = Preprocessor(output_step=2)
pp.set_generators([
    Gain(pp, t=10, smooth=2),
    Gain(pp, t=30, smooth=10),
    Gain(pp, t=120, smooth=30),
    Gain(pp, t=360, smooth=90),
#    Gain(pp, t=1800, smooth=450, last_n=1),
#    KD(pp, t=10, last_n=1),
    KD(pp, t=30, last_n=1),
    KD(pp, t=120, last_n=1),
#    KD(pp, t=360, last_n=1),
#    RSI(pp, t=10, last_n=1),
    RSI(pp, t=30, last_n=1),
    RSI(pp, t=120, last_n=1),
#    RSI(pp, t=360, last_n=1),
    ])
 
pp2 = Preprocessor(output_step=2)
pp2.set_generators([
    Gain(pp2, t=10, smooth=1, last_n=3, skip=2),
    Gain(pp2, t=30, smooth=1, last_n=3, skip=10),
    Gain(pp2, t=120, smooth=1, last_n=3, skip=30),
    Gain(pp2, t=360, smooth=1, last_n=3, skip=90),
#    Gain(pp2, t=1800, smooth=450, last_n=1),
#    KD(pp2, t=10, last_n=3, skip=3),
    KD(pp2, t=30, last_n=3, skip=10),
    KD(pp2, t=120, last_n=3, skip=30),
#    KD(pp2, t=360, last_n=3, skip=90),
#    RSI(pp2, t=10, last_n=3, skip=3),
    RSI(pp2, t=30, last_n=3, skip=10),
    RSI(pp2, t=120, last_n=3, skip=30),
#    RSI(pp2, t=360, last_n=3, skip=90),
    ])

ppv = Preprocessor(output_step=2)
ppv.set_generators([   
#    MA(ppv, input_key='open_vol', t=30),
#    MA(ppv, input_key='open_vol', t=120),
#    MA(ppv, input_key='open_vol', t=360),
#    MA(ppv, input_key='close_vol', t=30),
#    MA(ppv, input_key='close_vol', t=120),
#    MA(ppv, input_key='close_vol', t=360),
#    MA(ppv, input_key='pos_inc', t=30),
#    MA(ppv, input_key='pos_inc', t=120),
#    MA(ppv, input_key='pos_inc', t=360),
    Gain(ppv, input_key='vol', t=10, smooth=2, normalize=False),
    Gain(ppv, input_key='vol', t=30, smooth=10, normalize=False),
    Gain(ppv, input_key='vol', t=120, smooth=30, normalize=False),
    Gain(ppv, input_key='vol', t=360, smooth=90, normalize=False),
    MA(ppv, input_key='vol', t=10),
    MA(ppv, input_key='vol', t=30),
    MA(ppv, input_key='vol', t=120),
    MA(ppv, input_key='vol', t=360),
#    GainMA(pp, input_key='ask_vol', t=30, smooth=10, normalize=False, last_n=1),
    ])

print 'Building dataset...'
t0 = time.time()
Xd = pp.preprocess(ticks, output='X')
Xd2 = pp2.preprocess(ticks, output='X')
Xdv = ppv.preprocess(ticks, output='X')
Yd = pp.preprocess(ticks, output='Y', transaction_cost=.0005)
t1 = time.time()
print 'Done.', t1 - t0, 'seconds'


X = build(Xd)
X2 = build(Xd2)
Xv = build(Xdv, includes=['gain',])
Y = build(Yd, includes=['30',])
X_train, X_test = split(np.hstack([X, Xv]), extremum_cutoff=.001)
Y_train, Y_test = split(Y, extremum_cutoff=.001, normalize=False)
#mlp = build_mlp(X_train.shape[-1], Y_train.shape[-1], 30, 15)
#train(X_train, Y_train * 10000., X_test, Y_test * 10000, mlp, batch_size=1000)
