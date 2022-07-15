from multiprocessing import Process
import sys
import time
import signal
import socket
import glob
import numpy 

SERVER = socket.gethostbyname(socket.gethostname()) # The Server address is automatically found by checking the current computer's IP address
PORT = 5064 # Random port
ADDR = (SERVER, PORT)
API_DELIMINATOR = "¿"
disconnect_msg = "DISCONNECT"

graphData = 0
message_str = ""

Sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
def fileReader(thread_number):    
    signal.signal(signal.SIGINT, signal_handler)
    fName = './visualiser_demo_3/instrumentation_thread_' + str(thread_number) + '.csv'
    try:
        file_obj = open(fName, "rb")
        data = numpy.loadtxt(file_obj, delimiter=",",
                            skiprows=1, max_rows=50, usecols=(12, 13, 14, 15, 16, 18))      ### MAX ROW LIMIT IS MAX NUMBER OF TIME INSTANCES
    except Exception as e:
        print("Couldn't read thread " + str(thread_number) + " data because " + str(e))
    
    for s in (data):
        message_str = str(thread_number) + API_DELIMINATOR + str(s[0]) + API_DELIMINATOR + str(s[1]) + API_DELIMINATOR + str(s[2]) + API_DELIMINATOR + str(s[3]) + API_DELIMINATOR + str(s[4]) + API_DELIMINATOR + str(s[5])
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

    fpattern = './visualiser_demo_3/instrumentation_thread_*.csv'
    files = glob.glob(fpattern)
    processCount = len(files)
    print("number of threads is " + str(processCount))
    processes = []
    for i in range(processCount):
        processes.append(Process(target=fileReader, args=(i,)))
        processes[i].start()
        
    signal.signal(signal.SIGINT, signal_handler)
    
    for i in range(processCount):
        processes[i].join()
    Sock.sendto(disconnect_msg.encode('utf-8'), ADDR)
    

if __name__ == '__main__':
    main()