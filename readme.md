# Abstract #

Goal is to have a service running on exactly one machine in a two-member cluster.
I did not find something like this so I just created it. It is certainly not full-blown (only two cluster members, for example).

# Implementation #

Generally, the two cluster members are peers and make out the supervisor and worker roles on their own.

Process detection is done via TCP connections.
The script allows for the configuration of the command to run, the intervals where peers check their counterpart, and a fallback mode that pulls the command to a preferred machine.

An instance of the script is started on each host. One is elected as the
worker, executing a command in a loop. The other instance of the
script loops and checks  if the worker
is still available (by connecting to a network port). Once it detects that the worker is down, it assumes the worker role, starts its own network listener and executes
the command in a loop.

Supervisor and Worker election is based on multiple connection attempts to the peer, in random intervals.

This should work on Python 2.6.3+, no other dependecies required. Tested on Windows, Linux, Solaris.

# Usage #

```
Usage: ha_heartbeat.py [options] command

Options:
  -h, --help            show this help message and exit
  -l LOCAL_HOST_PORT, --local=LOCAL_HOST_PORT
                        local host and port in <host>:<port> format (default:
                        localhost:22221)
  -r REMOTE_HOST_PORT, --remote=REMOTE_HOST_PORT
                        remote host and port in <host>:<port> format (default:
                        localhost:22222)
  -t INTERVAL_TEST, --interval-test=INTERVAL_TEST
                        Maximum interval between peer checks (default: 10)
  --check-count=CHECK_COUNT
                        Number of times a supervisor will check a dead peer
                        before failing over. (default: 3)
  -i INTERVAL_COMMAND, --interval-commands=INTERVAL_COMMAND
                        Interval between command executions in seconds
                        (default: 30)
  -w WAIT_FOR_SERVERSOCKET, --wait-for-serversocket=WAIT_FOR_SERVERSOCKET
                        Wait seconds for the serversocket to become available
                        (default: 300)
  -m MODE, --mode=MODE  Start process in WORKER or SUPERVISOR mode (default:
                        SUPERVISOR)
  -f, --fallback        Fallback to peer once it is up again (default: False)
  -v, --verbose         Verbose output

```

# Examples #
Here are two usage examples:


  * Heartbeat command ("dir c:") executed every 30 seconds, pinned to one machine (m2), i.e., m1 takes over if m2 is down, as m2 comes back, m1 becomes supervisor again:

```
   h@m1 $ python ha_heartbeat.py -l m1:22221 -r m2:22222 -f "dir c:"
   h@m2 $ python ha_heartbeat.py -l m2:22222 -r m1:22221 -m WORKER "dir c:"
```

  * Heartbeat command ("ls -l") executed every 10 seconds, peer status checked every 5 seconds, no fallback once the supervisor takes over from a failed worker:

```
   h@m1 $ python ha_heartbeat.py -i 10 -t 5 -l m1:22221 -r m2:22222 "ls -l"
   h@m2 $ python ha_heartbeat.py -i 10 -t 5 -l m2:22222 -r m1:22221 "ls -l"
```
