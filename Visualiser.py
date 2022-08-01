import mailbox
import threading
import sys
import math
import socket
import signal
import numpy as np
import random
from bokeh.models import (ColorBar, ColumnDataSource, SingleIntervalTicker,
                          LinearColorMapper, PrintfTickFormatter, RangeTool, Range1d)
from bokeh.plotting import figure, curdoc
from bokeh.models import Button, Dropdown
from bokeh.layouts import column
from bokeh.transform import linear_cmap
from bokeh.palettes import Turbo256 as palette2



# Socket Configurations
############################################################################
API_DELIMINATOR = "-" 
PORT = 5064 # Random port
host = socket.gethostname()
SERVER = socket.getaddrinfo(host, PORT, socket.AF_INET6)
ADDR = (SERVER[0][4][0], PORT)
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_IP)
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)
sock.bind(ADDR)

#print(socket.getaddrinfo())
#sock.setblocking(0)
disconnect_msg = "DISCONNECT"



# POETS Configurations
############################################################################
ThreadCount = 64   # The actual number of threads present in a POETS box is 6144
ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount))
n = 16 # number of threads in a core
root_core = int(math.sqrt(ThreadCount / n))
CoreCount = root_core * root_core
maxRow = 0 # This is the number of time instances needed to plot the thread data


# Matrices for non-live Graphs, each index represents a thread and each element is a new time instance
# all per-core graphs
############################################################################
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



# Plot Configurations
############################################################################
row_x = [x + 0.5 for x in range(root_core)] #To define central square coordinates, a 0.5 offset is needed

core_count_x = []
for i in range(int(root_core)):
        core_count_x.extend(row_x)

core_count_y = []
for i in range(root_core):
    column_y = [i+0.5 for x in range(root_core)]
    core_count_y.extend(column_y)

#The ranges must be strings
rangex = list((str(x) for x in range(CoreCount)))

#Configurations for Heatmap - Used for TX/S values

heatmap = figure(width=800, height=300, toolbar_location = None, name = "heatmap",
           x_range=rangex, y_range=rangex, tools="")

#Extra tools available on the webpage
TOOLS="hover,crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,box_select,poly_select,"
TOOLTIPS = [("core", "$index"),
            ("TX/s", "@intensity")]
heatmap = figure(tools=TOOLS, tooltips = TOOLTIPS, title="Heat Map")

#The axis tick interval depends on the size of the graphs
if(root_core <= 20):
    jump = 1
else:
    jump = root_core/10
heatmap.xaxis.ticker = SingleIntervalTicker(interval=jump)
heatmap.yaxis.ticker = SingleIntervalTicker(interval=jump)
heatmap.yaxis.minor_tick_line_color = None  # turn off y-axis minor ticks
heatmap.xaxis.minor_tick_line_color = None  # turn off x-axis minor ticks

#Fixed heatmap color, going from light green to dark red
colors = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
bar_map = LinearColorMapper(palette = colors, low = 5000, high = 25000 )
color_bar = ColorBar(color_mapper=bar_map,
                ticker=SingleIntervalTicker(interval = 2500),
                formatter=PrintfTickFormatter(format="%d"+" TX/s"))

heatmap.add_layout(color_bar, 'right')


#Configurations for Line plot - Used for Cache Miss - Hit - WB values

line = figure(title = "Cache Data", tools = TOOLS, height=300, width=800, toolbar_location=None,
    x_axis_type="datetime", x_axis_location="above", y_axis_type="log", y_range=(10**2, 10**9),
    background_fill_color="#efefef", x_range=(0, 99))
line.xaxis.formatter = PrintfTickFormatter(format="%ss")

#Separated figure for the range selector, which allows to zoom in a specific section of time
select = figure(title="Drag the middle and edges of the selection box to change the range above",
            height=130, width=800, y_range=line.y_range,
            x_axis_type="datetime", y_axis_type=None,
        tools="", toolbar_location=None, background_fill_color="#efefef")
select.xaxis.formatter = PrintfTickFormatter(format="%ss")

layout = column(line, select, sizing_mode="scale_width", name="line")


#Configurations for Bar Chart - Used for CPUIDLE count

bar = figure(title="Bar Chart", name = "bar",
        toolbar_location=None, tools="")

bar.xgrid.grid_line_color = None
bar.axis.minor_tick_line_color = None
bar.outline_line_color = None
bar.yaxis.formatter = PrintfTickFormatter(format="%d%%")

#Configurations for Live Line Chart - Used for TX

TOOLTIPS2 = [("Thread", "$index")]
liveLine = figure(tools=TOOLS, tooltips = TOOLTIPS2, title = "Live Thread Instrumentation", name = "liveLine")
liveLine.x_range.follow="end"
liveLine.x_range.follow_interval = 30
liveLine.x_range.range_padding=0
liveLine.xaxis.formatter = PrintfTickFormatter(format="%ds")
liveLine.yaxis.formatter = PrintfTickFormatter(format="%d TX/s")


step = 1 # Step for X range
zero_list = [0] * 10
step_list = [i * step for i in range(10)]

ContainerX = np.empty((ThreadCount,), dtype = object)
ContainerY = np.empty((ThreadCount,), dtype = object)
colours = []
for i in range(len(ContainerY)): 
    ContainerY[i]=[0,0,0,0,0,0,0,0,0,0]
    ContainerX[i]=step_list 
    colours.append(random.choice(palette2))

bar.xgrid.grid_line_color = None
bar.axis.minor_tick_line_color = None
bar.outline_line_color = None
bar.yaxis.formatter = PrintfTickFormatter(format="%d%%")


kill = 0    # Variable used to kill threads
second_graph = 0 # Variable used to start other graphs
block = 0 # Variable used to freeze the Heatmap
gap1 = 16
gap2 = 1

def signal_handler(*args, **kwargs):
    print("\nTerminating Visualiser...")
    global kill
    kill = 1
    sock.close()
    print(f"active  {threading.active_count()}")
    sys.exit(0)

def stopper():
    global block, second_graph
    block = 1
    second_graph = 0

def clicker(event):
    global gap1, gap2
    print(event.item)
    if event.item == "MAILBOX":
        gap1 = 16 * 4
        gap2 = 4
        heatmap.renderers = []


    else:
        gap1 = 16
        gap2 = 1





def dataUpdater():
    print(" IN DATA UPDATER ")
    global ThreadLevel, cacheDataMiss, cacheDataHit, cacheDataMiss, second_graph, maxRow
    idx = 0
    while True:
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
                        ThreadLevel[idx] = float(splitMsg[7])
                        if not idx % n and idx/n < CoreCount:        ## Take only Thread 0 of each core as a representative of the entire core counter
                            if(maxRow < float(splitMsg[1])):       ## Count max number of rows, this determines Points to plot. Problem if fewer than 2 rows
                                maxRow = float(splitMsg[1])
                            cacheDataMiss[int(idx/n)].append(float(splitMsg[3]))
                            cacheDataHit[int(idx/n)].append(float(splitMsg[4]))
                            cacheDataWB[int(idx/n)].append(float(splitMsg[5]))
                            CPUIdle[int(idx/n)].append(float(splitMsg[6]))
                            blocked[int(idx/n)].append(float(splitMsg[2]))
                    else:
                        print("idx range is out of bound")
            except Exception as e:
                print("issue on thread " + str(idx) + " because: " + str(e))
        else:
            print(" killing data updater thread ")
            break


def plotterUpdater():
    print(" IN PLOTTER UPDATER ")
    print(f"active  {threading.active_count()}")

    if(second_graph):
        global kill
        kill = 1    # Stop other threads, no need for new data
        print(" RENDERING OTHER GRAPHS ")

        # Once numberPoints is known initiliase matrices
        numberPoints = int(maxRow) + 2      ## Add by two for the offset
        finalMiss = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalHit = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalWB = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalBlocked = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalIdle = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))

        for i in range(numberPoints):
            for k in range(CoreCount):
                try:
                    finalMiss[i] += cacheDataMiss[k][i+1]
                    finalHit[i] += cacheDataHit[k][i+1]
                    finalWB[i] += cacheDataWB[k][i+1]
                    finalBlocked[i] += blocked[k][i+1]    
                    finalIdle[i] += CPUIdle[k][i+1]/2100000    # Division by 21Mhz/100 to get time percentage
                except:
                    print("THREAD " + str(k) + " DOESN'T HAVE " + str(i) + " ROWS")

            # Average values to plot system view of Cache Miss Hit WB and CPUIDLE
            finalMiss[i] = finalMiss[i]/CoreCount
            finalHit[i] = finalHit[i]/CoreCount
            finalWB[i] = finalWB[i]/CoreCount
            finalBlocked[i] = finalBlocked[i]/CoreCount
            finalIdle[i] = finalIdle[i]/CoreCount
        
        #if stamement to check length of maximum and mim rows of threads to determine wether following division is needed
        # These values could be further group together between time istances
        #if(numberPoints > 100):
         #   w = math.ceil(numberPoints/100)
          #  nBlocked = [sum(finalBlocked[j:j+w])//n for j in range(0,len(finalBlocked),w)]
           # nIdle = [sum(finalIdle[j:j+w])//w for j in range(0,len(finalIdle),w)]
        #else:
         #   nblocked = finalBlocked
          #  nIdle = finalIdle

        # Creating ColumnDataSources for each graph, this is Bokeh's way of specifying data

        dataMiss = {'x_values': range(numberPoints),
                'y_values': finalMiss}
        sourceMiss = ColumnDataSource(data=dataMiss)

        dataHit = {'x_values': range(numberPoints),
                'y_values': finalHit}
        sourceHit = ColumnDataSource(data=dataHit)

        dataWB = {'x_values': range(numberPoints),
                'y_values': finalWB}
        sourceWB = ColumnDataSource(data=dataWB)

        line.line(x='x_values', y='y_values', source=sourceHit, legend="Cache Hit")
        line.line(x='x_values', y='y_values', source=sourceMiss, legend="Cache Miss", color = "red")
        line.line(x='x_values', y='y_values', source=sourceWB, legend="Cache WB", color = "green")


        range_tool = RangeTool(x_range=line.x_range)
        range_tool.overlay.fill_color = "navy"
        range_tool.overlay.fill_alpha = 0.2

        select.line('x_values', 'y_values', source=sourceMiss)
        select.ygrid.grid_line_color = None
        select.add_tools(range_tool)
        select.toolbar.active_multi = range_tool


        dataBar = {'x_values' : range(int(numberPoints)),
                'CPUIDLE'   : finalIdle}
        
        sourceBar = ColumnDataSource(data=dataBar)

        bar.vbar(x="x_values", top = "CPUIDLE", width=0.9, color="#718dbf", source = sourceBar, legend="CPUIDLE time")
        stopper()

    if not (block):

        length = CoreCount * n
        SelectedLevel = [sum(ThreadLevel[j:j+gap1])//gap1 for j in range(0, length, gap1)]
        selected_count_x = core_count_x[0:int(len(core_count_x)/gap2)]
        selected_count_y = core_count_y[0:int(len(core_count_y)/gap2)]

        print(SelectedLevel)
        print(str(len(core_count_y)/gap2))

        data = {'x_values' : selected_count_x,
            'y_values' : selected_count_y,
            'intensity': SelectedLevel}      # was ThreadLevel

        #create a ColumnDataSource by passing the dict
        source = ColumnDataSource(data=data)
        mapper = linear_cmap(field_name="intensity", palette=colors, low=5000, high=25000)
            
        latest = ContainerX[0][-1] + step
        for i in range(len(ContainerY)):
            ContainerY[i].append(ThreadLevel[i])
            ContainerY[i].pop(0)        # All values change equally

        ContainerX[0].append(latest)
        ContainerX[0].pop(0)        # All values change equally

        dataLine = {'x_value' : ContainerX,
            'y_value' : ContainerY,
            'colour': colours}

        source2 = ColumnDataSource(data=dataLine)  

        liveLine.multi_line(xs = "x_value", ys= "y_value", source = source2, line_color = "colour") 
        heatmap.rect(x='x_values',  y='y_values', width = 1, height = 1, source = source,
        line_color=None, fill_color=mapper)
    else:
        print(" blocking callback function ")



if sys.version_info[0] < 3:
    print("ERROR: Visualiser must be executed using Python 3")
    sys.exit(-1)

# Interrupt handler
signal.signal(signal.SIGINT, signal_handler)

# Data thread for storing data continuosly
dataThread = threading.Thread(name='data',target=dataUpdater)
dataThread.daemon = True
dataThread.start()

# Button to freeze execution of heatmap
button = Button(label="Stop")
button.on_click(stopper)

menu = Dropdown(label = "Select Hierarchy", menu = ["CORE", "MAILBOX", "BOARD", "BOX"])
menu.on_click(clicker)

curdoc().add_root(column(button, menu, heatmap, liveLine, layout, bar))
curdoc().add_periodic_callback(plotterUpdater, 500) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Ver
