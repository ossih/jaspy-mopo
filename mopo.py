from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import time
import json
import subprocess
import argparse


def read_interface(interfaces, nspid):
    total_byte = 0
    total_packet = 0
    if nspid is not None:
        file = f'/proc/{nspid}/net/dev'
    else:
        file = '/proc/net/dev'
    with open(file, encoding='utf8') as f:
        for row in f.readlines()[2:]:
            ifname, rawstat = row.strip().split(':')
            stats = rawstat.split()
            if ifname in interfaces:
                total_byte += int(stats[0])
                total_byte += int(stats[8])
                total_packet += int(stats[1])
                total_packet += int(stats[9])
    return total_byte, total_packet


def read_interface_ethtool(interfaces, nspid):
    total_byte = 0
    total_packet = 0
    cmd = []
    if nspid is not None:
        cmd = ['/usr/bin/nsenter', '-n', '-t', nspid]
    for iface in interfaces:
        icmd = cmd + ['/usr/sbin/ethtool', '-S', iface]
        p = subprocess.Popen(icmd, stdout=subprocess.PIPE)
        (stdout, stderr) = p.communicate()
        for row in stdout.decode("utf-8").splitlines():
            if row.strip().startswith("rx_bytes:") or row.strip().startswith("tx_bytes:"):
                byte = row.strip().split(":")[1].strip()
                total_byte += int(byte)
            if row.strip().startswith("rx_packets:") or row.strip().startswith("tx_packets:"):
                packet = row.strip().split(":")[1].strip()
                total_packet += int(packet)
    return total_byte, total_packet



def configure_handler(args):
    if args.use_ethtool:
        read_function = read_interface_ethtool
    else:
        read_function = read_interface

    nspid = args.nspid
    interfaces = args.interface

    class Handler(BaseHTTPRequestHandler):

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET")
            self.send_header("Access-Control-Allow-Headers", " X-Custom-Header")
            self.end_headers();
            self.wfile.write(b"")


        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache", "no-store")
            self.end_headers()
            byte, packet = read_function(interfaces, nspid)
            while True:
                byte_new, packet_new = read_function(interfaces, nspid)
                self.wfile.write(b'data: ' + json.dumps({"bps": (byte_new-byte)/0.1*8, "pps": (packet_new-packet)/0.1}).encode("utf-8") + b'\n\n')
                byte = byte_new
                packet = packet_new
                time.sleep(0.1)

    return Handler


class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--interface', required=True, action='append', help='wanted interfaces')
    parser.add_argument('-N', '--nspid', default=None, help='namespace pid')
    parser.add_argument('-E', '--use_ethtool', action='store_true', default=False, help='use ethtool instead of /proc')
    args = parser.parse_args()
    Handler = configure_handler(args)
    server = ThreadingSimpleServer(('0.0.0.0', 4444), Handler)
    server.serve_forever()


if __name__ == '__main__':
    run()
