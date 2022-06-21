from multiprocessing import Process, Queue
import threading
import random
import sys
import os
import datetime
import time
import signal
import socket
import glob
import csv
import numpy 

visAddr = "::1" #"127.0.0.1"
visPort = 9000

API_DELIMINATOR = "¿"

graphData = 0
message_str = ""

visSock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    
def fileReader(thread):
    print("Process thread " + str(thread) + " starting")
    
    signal.signal(signal.SIGINT, signal_handler)
    
    fName = 'instrumentation_thread_' + str(thread) + '.csv'
    #This needs a try-catch block and parameterisation
    file_obj = open(fName, "rb")
    try:
        data = numpy.loadtxt(file_obj, delimiter=",",
                            skiprows=1, max_rows=1400, usecols=(17))
    except Exception as e:
        print("Couldn't read thread " + str(thread) + " data because " + str(e))
    
    while True:
        for s in data:
            message_str = str(thread) + API_DELIMINATOR + str(s)
            visSock.sendto(message_str.encode('utf-8'), (visAddr, visPort))
            time.sleep(1)

def signal_handler(signal_in, frame):
    print("\nTerminating Sender...")
    sys.exit(0)
  
def main():
    if sys.version_info[0] < 3:
        print("ERROR: Sender must be executed using Python 3")
        sys.exit(-1)

    processes = []
    
    fpattern = 'instrumentation_thread_*.csv'
    files = glob.glob(fpattern)
    processCount = len(files)
    
    for i in range(processCount):
        processes.append(Process(target=fileReader, args=(i,)))
        processes[i].start()
        
    signal.signal(signal.SIGINT, signal_handler)
    
    for i in range(processCount):
        processes[i].join()
    

if __name__ == '__main__':
    main()