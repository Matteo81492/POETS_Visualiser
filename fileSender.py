import time
import sys
import signal
import socket
import numpy 

# Socket Configurations
############################################################################
API_DELIMINATOR = "-"
PORT = 5064 
# SERVER = socket.getaddrinfo(socket.gethostname(), PORT) # The Server address is automatically found by checking the current computer's IP address
ADDR = ("::1", PORT)    ## Local address for now
disconnect_msg = "DISCONNECT"
graphData = 0
message_str = ""

Sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
Sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)


def signal_handler(signal_in, frame):
    print("\nTerminating Sender...")
    sys.exit(0)
  

def main():
    current = 0  
    signal.signal(signal.SIGINT, signal_handler)
    fName = './new_data/instrumentation.csv'
    ## Loading the entire document so that data can be sent without interruptions at fixed intervals
    try:
        file_obj = open(fName, "rb")
        data = numpy.loadtxt(file_obj, delimiter=",",
                            skiprows=1, max_rows= None, usecols=(0, 1, 12, 13, 14, 15, 16, 18))
    except Exception as e:
        print("Couldn't open file because " + str(e))
    
    for s in (data):
        if(s[1]>current):   ## s[1] represents the time instance for the data packet, before a new time instance is sent, 1 second must be awaited
            current = s[1]
            time.sleep(1)
        message_str = str(s[0]) + API_DELIMINATOR + str(s[1]) + API_DELIMINATOR + str(s[2]) + API_DELIMINATOR + str(s[3]) + API_DELIMINATOR + str(s[4]) + API_DELIMINATOR + str(s[5]) + API_DELIMINATOR + str(s[6]) + API_DELIMINATOR + str(s[7])
        Sock.sendto(message_str.encode('utf-8'), ADDR)
        print(message_str)

    time.sleep(2)
    print("DISCONNECTING")

if __name__ == '__main__':
    main()
