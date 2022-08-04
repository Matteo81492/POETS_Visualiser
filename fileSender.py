from multiprocessing import Process
import multiprocessing
import sys
import time
import signal
import socket
import glob
import numpy 

PORT = 5064 # Random port
SERVER = socket.getaddrinfo(socket.gethostname(), PORT) # The Server address is automatically found by checking the current computer's IP address
ADDR = ("::1", PORT)
API_DELIMINATOR = "-"
disconnect_msg = "DISCONNECT"

graphData = 0
message_str = ""

Sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
Sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)

def fileReader(thread_number):    
    signal.signal(signal.SIGINT, signal_handler)
    fName = './visualiser_data/instrumentation_thread_' + str(thread_number) + '.csv'
    try:
        file_obj = open(fName, "rb")
        data = numpy.loadtxt(file_obj, delimiter=",",
                            skiprows=2, max_rows=10, usecols=(1, 12, 13, 14, 15, 16, 18))      ### MAX ROW LIMIT IS MAX NUMBER OF TIME INSTANCES
    except Exception as e:
        print("Couldn't read thread " + str(thread_number) + " data because " + str(e))
    
    for s in (data):
        message_str = str(thread_number) + API_DELIMINATOR + str(s[0]) + API_DELIMINATOR + str(s[1]) + API_DELIMINATOR + str(s[2]) + API_DELIMINATOR + str(s[3]) + API_DELIMINATOR + str(s[4]) + API_DELIMINATOR + str(s[5]) + API_DELIMINATOR + str(s[6])
        Sock.sendto(message_str.encode('utf-8'), ADDR)
        print(message_str)
        time.sleep(1)


def signal_handler(signal_in, frame):
    print("\nTerminating Sender...")
    sys.exit(0)
  
def main():
    if sys.version_info[0] < 3:
        print("ERROR: Sender must be executed using Python 3")
        sys.exit(-1)

    processes = []
    
    fpattern = './visualiser_data/instrumentation_thread_*.csv'
    files = glob.glob(fpattern)
    processCount = len(files)
    print("number of threads is " + str(processCount))
    for i in range(processCount):
        processes.append(Process(target=fileReader, args=(i,)))
        processes[i].start()
        
    signal.signal(signal.SIGINT, signal_handler)
    
    for i in range(processCount):
        processes[i].join()
    Sock.sendto(disconnect_msg.encode('utf-8'), ADDR)



    

if __name__ == '__main__':
    main()
