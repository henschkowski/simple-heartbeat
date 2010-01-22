#!python

"""
A simple high available heartbeat implementation. 

An instance of this is started on each host. One is elected as the
worker, executing a command in a loop. The other instance of the
script loops and checks by connecting to a network port if the worker
is still available. Once it detects that the worker is down, it
assumes the worker role, starts its own network listener and executes
the command in a loop.


Some examples:

  Heartbeat command ("dir c:") executed every 30 seconds, pinned to
  one machine (m2), i.e., m1 takes over if m2 is down, as m2 comes
  back, m1 becomes supervisor again:

    h@m1 $ python ha_heartbeat.py -l m1:22221 -r m2:22222 -fallback "dir c:"
    h@m2 $ python ha_heartbeat.py -l m2:22222 -r m1:22221 -mode WORKER "dir c:"


  Heartbeat command ("ls -l") executed every 10 seconds, peer status
  checked every 5 seconds, no fallback once the supervisor takes over
  from a failed worker:

    h@m1 $ python ha_heartbeat.py -i 10 -t 5 -l m1:22221 -r m2:22222 "ls -l"
    h@m2 $ python ha_heartbeat.py -i 10 -t 5 -l m2:22222 -r m1:22221 "ls -l"

  """

import socket
import threading
import SocketServer
import random
import time
from optparse import OptionParser
import logging
import subprocess
import sys

WORKER="WORKER"
SUPERVISOR="SUPERVISOR"
BIND_RETRY_WAIT = 30


class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):
        try:
            # The client only connects and does not send any data.
            pass
    
        except Exception as e:
            log.debug("Error in server handle(): %s" % (e,))
        

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


def client(ip, port, message="\n"):
    result = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((ip, port))
        result = True
    except Exception as e:
        log.debug("%s" % (e,))
    finally:
        if sock:
            sock.close()
    return result


def stop_listener_thread((listener, listener_thread)):
    if listener:
        listener.shutdown()
        listener = None
    if listener_thread:
        if listener_thread.is_alive():
            listener_thread.join(2)
        if listener_thread.is_alive():
            log.warning("Network listener thread still running.")
            return (listener, listener_thread)
        else:
            log.debug("Network listener thread successfully stopped.")
            return None


def start_listener_thread(local_host, local_port, wait_for_serversocket=300, bind_retry_wait=30):
    listener = listener_thread = None
    for retry in range(1, int(wait_for_serversocket) / BIND_RETRY_WAIT):
        try:
            listener = ThreadedTCPServer((local_host, local_port), ThreadedTCPRequestHandler)
                
            # Start a thread with the listener -- that thread
            # will then start one more thread for each request
            listener_thread = threading.Thread(target=listener.serve_forever)

            # Exit the listener thread when the main thread terminates
            listener_thread.setDaemon(True)
            listener_thread.start()
            log.debug("TCP Server loop running on host %s, port %s, in thread:%s" % (local_host, local_port, listener_thread.getName()))
            break
        except Exception as e:
            # This may happen if the socket is still in
            # TIME_WAIT mode. This can be tuned on the OS
            # level.
            log.info("Listener not running: %s" % (e))
            log.debug("Will try to start again in %d seconds." % (BIND_RETRY_WAIT))
            time.sleep(BIND_RETRY_WAIT)
    return (listener, listener_thread)


if __name__ == "__main__":
    usage_message = "Usage: %prog [options] command"
    parser = OptionParser(usage=usage_message)
    parser.add_option("-l", "--local", dest="local_host_port",
                      help="local host and port in <host>:<port> format (default: localhost:22221)", default="localhost:22221")
    parser.add_option("-r", "--remote", dest="remote_host_port",
                      help="remote host and port in <host>:<port> format (default: localhost:22222)", default="localhost:22222")
    parser.add_option("-t", "--interval-test", dest="interval_test",
                      help="Maximum interval between peer checks (default: 10)", default="10")
    parser.add_option("-c", "--check-count", dest="check_count",
                      help="Number of times a supervisor will check a dead peer before failing over. (default: 3)", default="3")
    parser.add_option("-i", "--interval-commands", dest="interval_command",
                      help="Interval between command executions in seconds (default: 30)", default="30")
    parser.add_option("-w", "--wait-for-serversocket", dest="wait_for_serversocket",
                      help="Wait seconds for the serversocket to become available (default: 300)", default="300")
    parser.add_option("-m", "--mode", dest="mode",
                      help="Start process in WORKER or SUPERVISOR mode (default: SUPERVISOR)", default=SUPERVISOR)
    parser.add_option("-f", "--fallback", dest="fallback", action="store_true", 
                      help="Fallback to peer once it is up again (default: False)", default=False)
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", 
                      help="Verbose output", default=False)

    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("Incorrect number of arguments. Try the -h or --help options for help.")

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    log = logging.getLogger(__file__)
        
    peer_host, peer_port = options.remote_host_port.split(':')
    local_host, local_port = options.local_host_port.split(':')
    log.debug("Peer host = %s, peer port = %s" % (peer_host, peer_port,))
    log.debug("Local host = %s, local port = %s" % (local_host, local_port,))
    checked = 0

    state = options.mode
    listener_details = None

    while True:
        if state == SUPERVISOR:
            sleepsecs = (random.random() * int(options.interval_test)) or 1
            if client(peer_host, int(peer_port)) != 0:
                if checked >= int(options.check_count):
                    log.warning("Peer is dead, now becoming a WORKER.")
                    state = WORKER
                else:
                    checked += 1
                    log.info("Peer is dead, check again in %f secs" % (sleepsecs,))
                    time.sleep(sleepsecs)
            else:
                log.debug("Peer is alive, next check in %f secs" % (sleepsecs,))
                checked = 0
                time.sleep(sleepsecs)

        elif state == WORKER:
            if not listener_details:
                listener_details = start_listener_thread(local_host, int(local_port), int(options.wait_for_serversocket))
                if listener_details[0] == None:
                    log.warning("Listener not started.")

            log.debug("Sanity check if peer is a WORKER ...:")
            if client(peer_host, int(peer_port)) == 0:
                if options.fallback == True:
                    log.info("Peer is alive, falling back to SUPERVISOR mode")
                    listener_details = stop_listener_thread(listener_details)
                    state = SUPERVISOR
                    continue
                else:
                    # Stay in WORKER mode, the other process should shut down.
                    log.info("Peer is an alive WORKER, but this process is also a WORKER")
            
            else:
                log.debug("Peer is still dead or in SUPERVISOR mode.")

            log.debug("Executing command ...")
            try:
                p = subprocess.Popen(args[0], shell=True, close_fds=True)
                p.communicate()
                rc = p.returncode
                if rc < 0:
                    log.warning("Command was terminated by signal %d" % (-rc,))
                else:
                    log.debug("Command executed with return code = %d" % (rc,))
                
            except OSError, e:
                log.warning("Command execution failed (%s)" % (e,))

            log.debug("Next job will run in %f seconds" % int(options.interval_command))
            time.sleep(int(options.interval_command))

        else:
            log.error("Unknown state %s. Exiting." % (state,))
            sys.exit(1)
        
