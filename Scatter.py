
from multiprocessing import Queue
import threading
import time
import sys
import signal
import socket
import numpy as np
from bokeh.plotting import figure, curdoc
from bokeh.layouts import column


# Socket config
############################################################################
API_DELIMINATOR = "¿"
SERVER = socket.gethostbyname(socket.gethostname()) # The Server address is automatically found by checking the current computer's IP address
PORT = 5064 # Random port
ADDR = (SERVER, PORT)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(ADDR)
# no options for now sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)



# Graphing Config
############################################################################
circleCount = 65     # How many circles (i.e. Threads) we show
TOOLS="hover,crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,box_select,poly_select,lasso_select,"
p = figure(tools=TOOLS)

# add a text renderer to the plot (no data yet)
renderer = p.scatter(x = [], y = [], radius=[],
        fill_color = [], fill_alpha=0.6,
        line_color=None)
ds = renderer.data_source
graphData = np.ndarray(circleCount, buffer=np.zeros(circleCount))
mainQueue = Queue()


def signal_handler(signal_in, frame):
    print("\nTerminating Visualiser...")
    sock.close()
    print("All Done!")
    sys.exit(0)


def bufferUpdater():
    print(" IN BUFFER UPDATER")
    global mainQueue
    mainQueue.put(graphData, False)


def get_queue():
    print(" IN QUEUE GETTER ")
    if not (mainQueue.empty()):
        return mainQueue.get()
    else:
        return np.ndarray(circleCount, buffer=np.zeros(circleCount))

def plotterUpdater():
    data, address = sock.recvfrom(65535)
    msg = data.decode("utf-8")

    dataThread = threading.Thread(name='data',target=dataUpdater, args=(msg,))
    dataThread.daemon = True
    dataThread.start()

    bufferThread = threading.Thread(name='buffer',target=bufferUpdater)
    bufferThread.daemon = True
    bufferThread.start()

    print(f"active  {threading.active_count()}")
    print(" IN PLOTTER UPDATER ")
    
    time.sleep(1) # plot data only after a second delay, but check for messages constantly
    
    current_data = get_queue()
    print(current_data)
    new_data = dict()
    new_data['x'] = range(circleCount)
    new_data['y'] = current_data[new_data['x']]
    new_data['radius'] = np.random.random(size = circleCount) * new_data['y'] * 0.05
    new_data['fill_color'] = np.array([ [r, g, 150] for r, g in zip(new_data['x'], new_data['y']) ], dtype="uint8")
    ds.data = new_data

def dataUpdater(msg):
    print(" IN DATA UPDATER ")
    try:
        splitMsg = msg.split(API_DELIMINATOR)
        idx = int(splitMsg[0])
        if idx < circleCount and idx >= 0:
            graphData[idx] = float(splitMsg[1])
        else:
            print("idx range is out of bound")
    except Exception as e:
        print(str(idx) + " couldn't be converted because " + str(e))

    
def main():
    if sys.version_info[0] < 3:
        print("ERROR: Visualiser must be executed using Python 3")
        sys.exit(-1)
    
    signal.signal(signal.SIGINT, signal_handler)

    
    
if __name__ == '__main__':
    main()

curdoc().add_root(column(p))
curdoc().add_periodic_callback(plotterUpdater, 1) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Ver