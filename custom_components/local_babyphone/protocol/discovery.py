"""Bounded native UDP discovery. No login, media session or device controls."""
import binascii
import ipaddress
import json
import re
import secrets
import socket
import struct
import time
from .wire import MAGIC,frame

PORT=6100


def normalize_ssid(value):
    value=value.strip()
    if not value:return ''
    if not re.fullmatch(r'phi_[0-9a-fA-F]{12}',value):raise ValueError('invalid_camera_ssid')
    return 'phi_'+value[4:].upper()


def query_packet(ssid,seq):
    ssid=normalize_ssid(ssid)
    if not ssid:raise ValueError('invalid_camera_ssid')
    return frame(2,seq,json.dumps({'ssid':ssid},separators=(',',':')).encode()+b'\0')


def matches_reply(data,seq,ssid):
    if not 11<=len(data)<=1024 or data[:4]!=MAGIC:return False
    size,op,reply_seq=struct.unpack_from('<HHB',data,6)
    if size!=len(data) or op!=0x8002 or reply_seq!=seq:return False
    if binascii.crc_hqx(data[6:],0x1234)!=struct.unpack_from('<H',data,4)[0]:return False
    try:info=json.loads(data[11:].rstrip(b'\0'))
    except (ValueError,UnicodeError):return False
    if not isinstance(info,dict):return False
    # The native receiver obtains the address from recvfrom(), not JSON.
    # It accepts a JSON device-query reply without an echoed SSID. If echoed,
    # require it to match the selective query. Authentication happens later.
    if 'ssid' in info and info['ssid']!=ssid:return False
    return True


def discover_camera(ssid,timeout=2,stop_event=None):
    """One selective broadcast; return the sole responder IP or None.

    The response is only an address hint. Never persist it until the regular
    pairing-key handshake succeeds. Do not log or expose response payloads.
    """
    ssid=normalize_ssid(ssid)
    if not ssid:raise ValueError('invalid_camera_ssid')
    if stop_event and stop_event.is_set():return None
    seq=secrets.randbelow(256)
    found=set()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.bind(('',0))
        sock.sendto(query_packet(ssid,seq),('255.255.255.255',PORT))
        deadline=time.monotonic()+timeout
        for _ in range(128):
            remaining=deadline-time.monotonic()
            if remaining<=0 or (stop_event and stop_event.is_set()):break
            sock.settimeout(min(.2,remaining))
            try:data,peer=sock.recvfrom(1025)
            except socket.timeout:continue
            if not matches_reply(data,seq,ssid):continue
            try:address=ipaddress.IPv4Address(peer[0])
            except ipaddress.AddressValueError:continue
            if address.is_multicast or address.is_unspecified or address.is_loopback or str(address)=='255.255.255.255':continue
            found.add(str(address))
    if len(found)>1:raise ValueError('discovery_ambiguous')
    return next(iter(found),None)
