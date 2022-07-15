from concurrent.futures import thread
from multiprocessing import Queue
from re import S #Threading concurrent, truly parallel
import threading
import sys
import math
import socket
import signal
import numpy as np
import time
from bokeh.models import (ColorBar, ColumnDataSource, SingleIntervalTicker,
                          LinearColorMapper, PrintfTickFormatter, RangeTool)
from bokeh.plotting import figure, curdoc
from bokeh.models import Button
from bokeh.layouts import column
from bokeh.transform import linear_cmap



############################################################################
API_DELIMINATOR = "¿" 
SERVER = socket.gethostbyname(socket.gethostname()) # The Server address is automatically found by checking the current computer's IP address
PORT = 5064 # Random port
ADDR = (SERVER, PORT)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(ADDR)
#sock.setblocking(0)
# no options for now sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)



# Graphing Config
############################################################################
threadNumber = 100   # This value should be transmitted
root = int(math.sqrt(threadNumber))
ThreadCount = root*root #To draw square we cant accept a float root
ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount))

n = 4 # number of threads in a core
root_core = int(math.sqrt(ThreadCount / n))
CoreCount = root_core * root_core

cacheDataMiss=np.empty((CoreCount,), dtype = object)
for i,v in enumerate(cacheDataMiss): 
    cacheDataMiss[i]=[0,0]

cacheDataHit=np.empty((CoreCount,), dtype = object)
for i,v in enumerate(cacheDataHit): 
    cacheDataHit[i]=[0,0]

cacheDataWB=np.empty((CoreCount,), dtype = object)
for i,v in enumerate(cacheDataWB): 
    cacheDataWB[i]=[0,0]

blocked=np.empty((CoreCount,), dtype = object)
for i,v in enumerate(blocked): 
    blocked[i]=[0,0]

CPUIdle=np.empty((CoreCount,), dtype = object)
for i,v in enumerate(CPUIdle): 
    CPUIdle[i]=[0,0]



numberPoints = 50 #for now fixed it at 100
finalMiss = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
finalHit = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
finalWB = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
finalBlocked = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))  #Change size of these structure
finalIdle = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))


#To define square coordinates, a 0.5 offset is needed
row_x = [x + 0.5 for x in range(root_core)]
core_count_x = []
for i in range(int(root_core)):
        core_count_x.extend(row_x)

###THE SAME ?

core_count_y = []
for i in range(root_core):
        column_y = [i+0.5 for x in range(root_core)]
        core_count_y.extend(column_y)

#The ranges must be strings
rangex = list((str(x) for x in range(CoreCount)))
rangey = list((str(y) for y in range(CoreCount)))

#For bigger set of data waves through cores, for small one static on the cores
#get core position from thread ID, index thread number gives mailbox info, mailbox has four corse with individual counters, Tinsel Documentation

p = figure(width=800, height=300, title="Heat Map", toolbar_location = None,
           x_range=rangex, y_range=rangey, tools="")

TOOLS="hover,crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,box_select,poly_select,lasso_select,"
TOOLTIPS = [("core", "$index"),
            ("TX/s", "@intensity")]
p = figure(tools=TOOLS, tooltips = TOOLTIPS)

#The tick interval depends on the size of the graphs
if(root <= 20):
    jump = 1
else:
    jump = root/10
p.xaxis.ticker = SingleIntervalTicker(interval=jump)
p.yaxis.ticker = SingleIntervalTicker(interval=jump)
p.yaxis.minor_tick_line_color = None  # turn off y-axis minor ticks
p.xaxis.minor_tick_line_color = None  # turn off x-axis minor ticks

#Fixed heatmap color, going from light green to dark red
colors = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
bar_map = LinearColorMapper(palette = colors, low = 5000, high = 25000 )
color_bar = ColorBar(color_mapper=bar_map,
                ticker=SingleIntervalTicker(interval = 2500),
                formatter=PrintfTickFormatter(format="%d"+" TX/s"))

p.add_layout(color_bar, 'right')


#Second figure for the line graph
p2 = figure(height=300, width=800, tools="xpan", toolbar_location=None,
    x_axis_type="datetime", x_axis_location="above", y_axis_type="log", y_range=(10**2, 10**9),
    background_fill_color="#efefef", x_range=(0, 99))
p2.xaxis.formatter = PrintfTickFormatter(format="%ss")

#Separed figure for the range selector
select = figure(title="Drag the middle and edges of the selection box to change the range above",
            height=130, width=800, y_range=p2.y_range,
            x_axis_type="datetime", y_axis_type=None,
        tools="", toolbar_location=None, background_fill_color="#efefef")
select.xaxis.formatter = PrintfTickFormatter(format="%ss")

p3 = figure(title="Bar Chart",
        toolbar_location=None, tools="")

#p3.y_range.start = 0
#p3.x_range.range_padding = 0.1
p3.xgrid.grid_line_color = None
p3.axis.minor_tick_line_color = None
p3.outline_line_color = None
p3.legend.location = "top_right"
p3.legend.orientation = "horizontal"
p3.yaxis.formatter = PrintfTickFormatter(format="%d%%")



MissQueue = Queue()
MissQueue.put(cacheDataMiss)
HitQueue = Queue()
HitQueue.put(cacheDataHit)
WBQueue = Queue()
WBQueue.put(cacheDataWB)

disconnect_msg = "DISCONNECT"
kill = 0
second_graph = 0
block = 0

def signal_handler(*args, **kwargs):
    print("\nTerminating Visualiser...")
    global kill
    kill = 1
    #time.sleep(5)
    sock.close()
    print("All Done!")
    print(f"active  {threading.active_count()}")
    sys.exit(0)

def stopper():
    #signal_handler()
    # for now just does same as signal handler, in future will stop and restart from current execution?
    global block
    block = ~block

def dataUpdater():
    print(" IN DATA UPDATER ")
    global ThreadLevel, cacheDataMiss, cacheDataHit, cacheDataMiss, second_graph
    while True:
        print(" Still in It ")
        if not(kill):
            try:
                data, address = sock.recvfrom(65535)
                msg = data.decode("utf-8")
                if(msg == disconnect_msg):
                    second_graph = 1      ##WHEN DISCONNECTION HAPPENS RUN OTHER GRAPHS
                else:
                    splitMsg = msg.split(API_DELIMINATOR)
                    idx = int(splitMsg[0])
                    if idx < ThreadCount and idx >= 0:
                        ThreadLevel[idx] = float(splitMsg[6])
                        if not idx % n and idx/n < CoreCount:        ## Take only Thread 0 of each core as a representative of the entire core counter
                            cacheDataMiss[int(idx/n)].append(float(splitMsg[2]))
                            cacheDataHit[int(idx/n)].append(float(splitMsg[3]))
                            cacheDataWB[int(idx/n)].append(float(splitMsg[4]))
                            CPUIdle[int(idx/n)].append(float(splitMsg[5]))
                            blocked[int(idx/n)].append(float(splitMsg[1]))


                    else:
                        print("idx range is out of bound")
            except Exception as e:        ## error raised due to socket problems cause end of thread
                print("issue on thread " + str(idx+1) + " because: " + str(e))

        else:
            print(" killing data updater thread ")
            break


def bufferUpdater():
    print(" IN BUFFER UPDATER")
    global CoreLevel, second_graph
    while True:
        if not(kill):
            length = CoreCount * n
            CoreLevel = [sum(ThreadLevel[j:j+n])//n for j in range(0, length ,n)]
        else:
            print(" killing buffer updater thread ")
            second_graph = 0
            break
    time.sleep(0.1)    

def plotterUpdater():
    print(" IN PLOTTER UPDATER ")
    print(f"active  {threading.active_count()}")

    if(second_graph):
        global kill, block
        block = 1
        kill = 1
        print(" RENDERING SECOND GRAPH ")
        for i in range(numberPoints):
            for k in range(CoreCount):
                try:
                    finalMiss[i] += cacheDataMiss[k][i]
                    finalHit[i] += cacheDataHit[k][i]
                    finalWB[i] += cacheDataWB[k][i]
                    finalBlocked[i] += blocked[k][i]    # change here to take into account more time points, then divide them
                    finalIdle[i] += CPUIdle[k][i]/2100000    # change here to take into account more time points, then divide them
                except:
                    print("THREAD " + str(k) + " DOESN'T HAVE " + str(i) + " ROWS")


            finalMiss[i] = finalMiss[i]/CoreCount
            finalHit[i] = finalHit[i]/CoreCount
            finalWB[i] = finalWB[i]/CoreCount
            finalBlocked[i] = finalBlocked[i]/CoreCount
            finalIdle[i] = finalIdle[i]/CoreCount
        
        #if stamement to check length of maximum and mim rows of threads to determine wether following division is needed
        w = 5
        nBlocked = [sum(finalBlocked[j:j+w])//n for j in range(0,len(finalBlocked),w)]
        nIdle = [sum(finalIdle[j:j+w])//w for j in range(0,len(finalIdle),w)]

        dataMiss = {'x_values': range(numberPoints),
                'y_values': finalMiss}
        sourceMiss = ColumnDataSource(data=dataMiss)

        dataHit = {'x_values': range(numberPoints),
                'y_values': finalHit}
        sourceHit = ColumnDataSource(data=dataHit)

        dataWB = {'x_values': range(numberPoints),
                'y_values': finalWB}
        sourceWB = ColumnDataSource(data=dataWB)

        p2.line(x='x_values', y='y_values', source=sourceHit, legend="Cache Hit")
        p2.line(x='x_values', y='y_values', source=sourceMiss, legend="Cache Miss", color = "red")
        p2.line(x='x_values', y='y_values', source=sourceWB, legend="Cache WB", color = "green")


        range_tool = RangeTool(x_range=p2.x_range)
        range_tool.overlay.fill_color = "navy"
        range_tool.overlay.fill_alpha = 0.2

        select.line('x_values', 'y_values', source=sourceMiss)
        select.ygrid.grid_line_color = None
        select.add_tools(range_tool)
        select.toolbar.active_multi = range_tool


        dataBar = {'x_values' : range(int(numberPoints)),
                'CPUIDLE'   : finalIdle}
        
        sourceBar = ColumnDataSource(data=dataBar)

        p3.vbar(x="x_values", top = "CPUIDLE", width=0.9, color="#718dbf", source = sourceBar, legend="CPUIDLE time")

    if not (block):
        print(CoreLevel)

        data = {'x_values' : core_count_x,
            'y_values' : core_count_y,
            'intensity': CoreLevel}      # was ThreadLevel

        #create a ColumnDataSource by passing the dict
        source = ColumnDataSource(data=data)
        mapper = linear_cmap(field_name="intensity", palette=colors, low=5000, high=25000)

        # add a text renderer to the plot (no data yet)
        p.rect(x='x_values',  y='y_values', width = 1, height = 1, source = source,
        line_color=None, fill_color=mapper)


    else:
        print(" blocking callback function ")




if sys.version_info[0] < 3:
    print("ERROR: Visualiser must be executed using Python 3")
    sys.exit(-1)

signal.signal(signal.SIGINT, signal_handler)


dataThread = threading.Thread(name='data',target=dataUpdater)
dataThread.daemon = True
dataThread.start()


bufferThread = threading.Thread(name='buffer',target=bufferUpdater)
bufferThread.daemon = True
bufferThread.start()

button = Button(label="Stop")
button.on_click(stopper)

curdoc().add_root(column(button, p, p2, select, p3))
curdoc().add_periodic_callback(plotterUpdater, 1000) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Ver
#curdoc().add_root(column(p2, select))
#curdoc().add_periodic_callback(other_graphs, 500) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Ver
