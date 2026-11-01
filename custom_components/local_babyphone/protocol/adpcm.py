"""16-bit mono IMA/DVI ADPCM in the high-nibble-first device format."""
from array import array
import sys

STEPS=(7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767)
INDEX=(-1,-1,-1,-1,2,4,6,8)


def _advance(code, predictor, index):
    step=STEPS[index]
    delta=step>>3
    if code&4:delta+=step
    if code&2:delta+=step>>1
    if code&1:delta+=step>>2
    predictor=max(-32768,min(32767,predictor-delta if code&8 else predictor+delta))
    return predictor,max(0,min(88,index+INDEX[code&7]))


def decode(data, width=2, state=(0,0)):
    if width!=2 or not 0<=state[1]<=88:raise ValueError('Invalid ADPCM state')
    predictor,index=state
    samples=array('h')
    for byte in data:
        for code in (byte>>4,byte&15):
            predictor,index=_advance(code,predictor,index)
            samples.append(predictor)
    if sys.byteorder!='little':samples.byteswap()
    return samples.tobytes(),(predictor,index)


def encode(data, width=2, state=(0,0)):
    if width!=2 or len(data)%2 or not 0<=state[1]<=88:raise ValueError('Invalid PCM or ADPCM state')
    samples=array('h');samples.frombytes(data)
    if sys.byteorder!='little':samples.byteswap()
    predictor,index=state
    output=bytearray();pending=None
    for sample in samples:
        difference=sample-predictor
        code=8 if difference<0 else 0
        difference=abs(difference);step=STEPS[index]
        for flag in (4,2,1):
            if difference>=step:code|=flag;difference-=step
            step>>=1
        predictor,index=_advance(code,predictor,index)
        if pending is None:pending=code<<4
        else:output.append(pending|code);pending=None
    return bytes(output),(predictor,index)


adpcm2lin=decode
lin2adpcm=encode


def rms(data, width=2):
    if width!=2 or len(data)%2:raise ValueError('16-bit PCM required')
    samples=array('h');samples.frombytes(data)
    if sys.byteorder!='little':samples.byteswap()
    return int((sum(s*s for s in samples)/len(samples))**.5) if samples else 0
