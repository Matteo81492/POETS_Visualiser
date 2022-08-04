''' This file generates a dashboard that includes a live heatmap and multiline chart of the 
    POETS data that is received through the socket. After the application run is over, a bar chart
    and a line graph show idle and cache values respectively. The dashboard follows a Bootstrap
    template and is shown locally.
'''
import threading
import sys
import math
import socket
import time
import signal
import numpy as np
import random
from bokeh.models import (ColorBar, ColumnDataSource, SingleIntervalTicker,
                          LinearColorMapper, PrintfTickFormatter, RangeTool, HoverTool,
                          NumberFormatter, RangeTool, StringFormatter, TableColumn)
from bokeh.plotting import figure, curdoc
from bokeh.models.widgets import DataTable, TableColumn
from bokeh.models import Button, Dropdown
from bokeh.layouts import column
from bokeh.transform import linear_cmap
from bokeh.palettes import Turbo256 as palette2

# Socket Configurations
############################################################################
API_DELIMINATOR = "-" 
PORT = 5064 # Random port
host = socket.gethostname()
SERVER = socket.getaddrinfo(host, PORT, socket.AF_INET6)    ## Automatically get local IPV6 Address 
ADDR = (SERVER[0][4][0], PORT)
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_IP) ## Create UDP socket
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)
sock.bind(ADDR)
disconnect_msg = "DISCONNECT"



# POETS Configurations
############################################################################
refresh_rate = 250 ## Time in millisecond for updating live plots
ThreadCount = 49152   # The actual number of threads present in a POETS box is 6144 - 49152 in total
ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount))
n = 16 # number of threads in a core
root_core = int(math.sqrt(ThreadCount / n))
root_mailbox = int(math.sqrt(ThreadCount / 64))
root_board = int(math.sqrt(ThreadCount / 1024))
root_box = int(math.sqrt(ThreadCount / 6144))


CoreCount = root_core * root_core
maxRow = 0 # This is the number of time instances needed to plot the thread data

execution_time = 0
usage = 0

# Matrices for non-live Graphs, each index represents a thread and each element is a new time instance
# all per-core graphs
############################################################################
cacheDataMiss=np.empty((CoreCount,), dtype = object)
cacheDataHit=np.empty((CoreCount,), dtype = object)
cacheDataWB=np.empty((CoreCount,), dtype = object)
CPUIdle=np.empty((CoreCount,), dtype = object)

for i,v in enumerate(range(CoreCount)): 
    cacheDataMiss[i]=[0,0]
    cacheDataHit[i]=[0,0]
    cacheDataWB[i]=[0,0]
    CPUIdle[i]=[0,0]


# Plot Configurations
############################################################################
row_x = [x + 0.5 for x in range(root_core)] #To define central square coordinates, a 0.5 offset is needed
core_count_x = []
core_count_y = []
for i in range(root_core):
    core_count_x.extend(row_x)
    column_y = [i+0.5 for x in range(root_core)]
    core_count_y.extend(column_y)

row_x = [x + 0.5 for x in range(root_mailbox)]
mailbox_count_x = []
mailbox_count_y = []
for i in range(root_mailbox):
    mailbox_count_x.extend(row_x)
    column_y = [i+0.5 for x in range(root_mailbox)]
    mailbox_count_y.extend(column_y)

row_x = [x + 0.5 for x in range(root_board)]
board_count_x = []
board_count_y = []
for i in range(root_board+2):     ## + 2 because two extra rows are needed to reach 48 board count
    board_count_x.extend(row_x)
    column_y = [i+0.5 for x in range(root_board)]
    board_count_y.extend(column_y)

row_x = [x + 0.5 for x in range(root_box)]
box_count_x = []
box_count_y = []
for i in range(root_box+2):     ## + 2 because two extra rows are needed to reach 8 box count
    box_count_x.extend(row_x)
    column_y = [i+0.5 for x in range(root_box)]
    box_count_y.extend(column_y)


#The ranges must be strings
rangex = list((str(x) for x in range(CoreCount)))

#Configurations for Heatmap - Used for TX/S values

heatmap = figure(height=300, toolbar_location = None,
           x_range=rangex, y_range=rangex, tools="")

#Extra tools available on the webpage
TOOLS="crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,box_select,poly_select,"

TOOLTIPS = [("core", "$index"),
            ("TX/s", "@intensity")]

#Set the default option for the Hovertool tooltips
hover=HoverTool(tooltips=TOOLTIPS)
heatmap = figure(height = 590, width = 560, tools=[hover, TOOLS], title="Heat Map",  name = "heatmap", toolbar_location="below")

TOOLS="hover,crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,box_select,poly_select,"



#The axis tick interval depends on the size of the graphs
if(root_core <= 20):
    jump = 1
else:
    jump = root_core/10
heatmap.xaxis.ticker = SingleIntervalTicker(interval=jump)
heatmap.yaxis.ticker = SingleIntervalTicker(interval=jump)
heatmap.yaxis.minor_tick_line_color = None  # turn off y-axis minor ticks
heatmap.xaxis.minor_tick_line_color = None  # turn off x-axis minor ticks
heatmap.toolbar.logo = None

#Fixed heatmap color, going from light green to dark red
colors = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
bar_map = LinearColorMapper(palette = colors, low = 5000, high = 25000 )
color_bar = ColorBar(color_mapper=bar_map,
                ticker=SingleIntervalTicker(interval = 2500),
                formatter=PrintfTickFormatter(format="%d"+" TX/s"))

heatmap.add_layout(color_bar, 'right')




#Configurations for Line plot - Used for Cache Miss - Hit - WB values
TOOLTIPS = [("second", "$index"),
            ("value", "@y_values")]
line = figure(width = 720, title = "Line Graph", tools = TOOLS, tooltips = TOOLTIPS, height=300, toolbar_location="below",
    x_axis_type="datetime", x_axis_location="above", y_axis_type="log", y_range=(10**2, 10**9),
    background_fill_color="#efefef", x_range=(0, 99))
line.toolbar.logo = None
line.xaxis.formatter = PrintfTickFormatter(format="%ss")

Hit_line = line.line(x=[], y=[], legend="Cache Hit")
Miss_line = line.line(x=[], y=[], legend="Cache Miss", color = "red")
WB_line = line.line(x=[], y=[], legend="Cache WB", color = "green")

Hit_line_ds = Hit_line.data_source
Miss_line_ds = Miss_line.data_source
WB_line_ds = WB_line.data_source

#Separated figure for the range selector, which allows to zoom in a specific section of time
select = figure(width = 720, title="Drag the middle and edges of the selection box to change the range above",
            height=130, y_range=line.y_range,
            x_axis_type="datetime", y_axis_type=None,
        tools="", toolbar_location=None, background_fill_color="#efefef")
select.xaxis.formatter = PrintfTickFormatter(format="%ss")
select.ygrid.grid_line_color = None

selectO = select.line(x = [], y =[])
select_ds = selectO.data_source

layout = column(line, select, sizing_mode="scale_width", name="line")

#Configurations for Bar Chart - Used for CPUIDLE count

TOOLTIPS = [("second", "$index"),
            ("percentage", "@CPUIDLE")]

bar = figure(height = 580, width = 490, title="Bar Chart", name = "bar",
        toolbar_location="below", tools=TOOLS, tooltips = TOOLTIPS, y_range = (0, 100))
bar.toolbar.logo = None
bar.xgrid.grid_line_color = None
bar.axis.minor_tick_line_color = None
bar.outline_line_color = None
bar.yaxis.formatter = PrintfTickFormatter(format="%d%%")
bar.xaxis.formatter = PrintfTickFormatter(format="%ss")
bar.xaxis.ticker = SingleIntervalTicker(interval=1)
bar.yaxis.ticker = SingleIntervalTicker(interval=10)

barO = bar.vbar(x=[], top = [], width=0.2, color="#718dbf")
bar_ds = barO.data_source



#Configurations for Live Line Chart - Used for TX


TOOLTIPS = [("Thread", "$index")]
liveLine = figure(height = 590, width = 720, tools=TOOLS, tooltips = TOOLTIPS, title = "Live Thread Instrumentation", name = "liveLine", toolbar_location="below", y_axis_location = "right")
liveLine.toolbar.logo = None
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
    colours.append(random.choice(palette2)) #### try to eliminate random


liveLineO = liveLine.multi_line(xs = [], ys= [], line_color = []) 
liveLine_ds = liveLineO.data_source

## Configuration for text graph showing post-run parameters
tdata = {'Application' : ["current","previous"],
            'Execution Time' : [0,0],
            'Average Utilisation': [0,0]}  
source = ColumnDataSource(data=tdata)
columns = [
    TableColumn(field="Application", title="Application"),
    TableColumn(field="Execution Time", title="Execetution Time (s)",
                formatter=StringFormatter(text_align="center")),
    TableColumn(field="Average Utilisation", title="Average Utilisation (TX/s)",
                formatter=NumberFormatter(text_align="right")),
]
table = DataTable(source=source, columns=columns, height=210, width=330, name="table", sizing_mode="scale_both")

curdoc().add_root(table)

table_ds = table.source


second_graph = 0 # Variable used to start other graphs
block = 0 # Variable used to freeze the Heatmap
gap1 = 16
gap2 = 1
range_tool_active = 0


def signal_handler(*args, **kwargs):
    print("\nTerminating Visualiser...")
    sock.close()
    print(f"active  {threading.active_count()}")
    sys.exit(0)


def stopper():
    global block
    print("STOPPING live data")
    block = ~block

def clicker(event):
    global gap1, gap2
    print(event.item)
    heatmap.renderers = []
    if event.item == "BOX":
        gap1 = 6144
        gap2 = 384
        heatmap.tools[0].tooltips = [("box", "$index"),
                                    ("TX/s", "@intensity")]
    elif event.item == "BOARD":
        gap1 = 1024
        gap2 = 64
        heatmap.tools[0].tooltips = [("board", "$index"),
                                    ("TX/s", "@intensity")]
    elif event.item == "MAILBOX":
        gap1 = 64
        gap2 = 4
        heatmap.tools[0].tooltips = [("mailbox", "$index"),
                                    ("TX/s", "@intensity")]
    else:
        gap1 = 16
        gap2 = 1
        heatmap.tools[0].tooltips = [("core", "$index"),
                                    ("TX/s", "@intensity")]


def dataUpdater():
    print(" IN DATA UPDATER ")
    global ThreadLevel, cacheDataMiss, cacheDataHit, cacheDataWB, CPUIdle, second_graph, maxRow, CPUIdle
    idx = 0
    while True:
        try:
            data, address = sock.recvfrom(65535)    ## Potential Bottleneck, no parallel behaviour, look into network buffering
            msg = data.decode("utf-8")
            if(msg == disconnect_msg):
                second_graph = 1      ##WHEN DISCONNECTION HAPPENS RUN OTHER GRAPHS
                line.renderers = []
                bar.renderers = []
                select.renderers = []
                heatmap.renderers = []
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
                else:
                    print("idx range is out of bound")
        except Exception as e:
            print("issue on thread " + str(idx) + " because: " + str(e))



def plotterUpdater():
    global second_graph, ThreadLevel, cacheDataMiss, cacheDataHit, cacheDataWB, CPUIdle, maxRow, execution_time, usage, range_tool_active

    print(" IN PLOTTER UPDATER ")
    print(f"active  {threading.active_count()}")

    if(second_graph):
        print(" RENDERING OTHER GRAPHS ")
        execution_time2 = execution_time
        usage2 = usage
        # Once numberPoints is known initiliase matrices, This could be guessed at the start thus saving time for the execution
        numberPoints = int(maxRow) + 2      ## Add by two for the offset
        execution_time = maxRow + 1     ## The maximum number of rows indicates the total execution time in seconds
        finalMiss = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalHit = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalWB = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))
        finalIdle = np.ndarray(numberPoints, buffer=np.zeros(numberPoints))

        for i in range(numberPoints):
            for k in range(CoreCount):
                try:
                    finalMiss[i] += cacheDataMiss[k][i+1]
                    finalHit[i] += cacheDataHit[k][i+1]
                    finalWB[i] += cacheDataWB[k][i+1]
                    finalIdle[i] += CPUIdle[k][i+1]
                except:
                    print("CORE " + str(k) + " DOESN'T HAVE ROW" + str(i))
                    finalIdle[i] += 100   # If the value of the core is not reachable, it means that no work was done, hence 100% idle for that time slot


            # Average values to plot system view of Cache Miss Hit WB and CPUIDLE
            finalMiss[i] = finalMiss[i]/CoreCount
            finalHit[i] = finalHit[i]/CoreCount
            finalWB[i] = finalWB[i]/CoreCount
            finalIdle[i] = finalIdle[i]/(CoreCount * 2100000)    # Division by 21Mhz/100 to get time percentage
        
        dataMiss = {'x': range(numberPoints),
                'y': finalMiss}

        dataHit = {'x': range(numberPoints),
                'y': finalHit}

        dataWB = {'x': range(numberPoints),
                'y': finalWB}

        Miss_line_ds.data = dataMiss
        Hit_line_ds.data = dataHit
        WB_line_ds.data = dataWB
        select_ds.data = dataMiss

        range_tool = RangeTool(x_range=line.x_range)
        range_tool.overlay.fill_color = "navy"
        range_tool.overlay.fill_alpha = 0.2

        if(range_tool_active == 0):
            select.add_tools(range_tool)
            select.toolbar.active_multi = range_tool

        range_tool_active = 1

        dataBar = {'x' : range(int(numberPoints)),
                'top'   : finalIdle}
        
        bar_ds.data = dataBar

        total = 0 # value holders for resource utilisation parameter ### bottleneck maybe
        for e in range(len(ThreadLevel)):
            total += np.sum(ThreadLevel[e])

        usage = round(total/execution_time, 3)
        newTable = {'Application' : table_ds.data['Application'],
                'Execution Time'   : [execution_time, execution_time2],
                'Average Utilisation' : [usage, usage2]}

        table_ds.data = newTable

        #######REFRESHING
        print("REFRESSSSSSSSSSSSSSSSSSSSSSSSSSSSSH")

        for i,v in enumerate(range(CoreCount)): 
            cacheDataMiss[i]=[0,0]
            cacheDataHit[i]=[0,0]
            cacheDataWB[i]=[0,0]
            CPUIdle[i]=[0,0]

        ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount))

        second_graph = 0


    if not (block):
        if(gap1 == 16):                     ## CORE VIEW
            length = len(core_count_x) * gap1
            selected_count_x = core_count_x
            selected_count_y = core_count_y
            SelectedLevel = [sum(ThreadLevel[j:j+n])//n for j in range(0, length ,n)]


        elif(gap1 == 64):                   ## MAILBOX VIEW
            length = len(mailbox_count_x) * gap1
            selected_count_x = mailbox_count_x
            selected_count_y = mailbox_count_y
            SelectedLevel = [sum(ThreadLevel[j:j+gap1])//gap1 for j in range(0, length, gap1)]

        elif(gap1 == 1024):                 ## BOARD VIEW
            length = len(board_count_x) * gap1
            selected_count_x = board_count_x
            selected_count_y = board_count_y
            SelectedLevel = [sum(ThreadLevel[j:j+gap1])//gap1 for j in range(0, length, gap1)]

        else:                               ## BOX VIEW
            length = len(box_count_x) * gap1
            selected_count_x = box_count_x
            selected_count_y = box_count_y
            SelectedLevel = [sum(ThreadLevel[j:j+gap1])//gap1 for j in range(0, length, gap1)]

        heatmap_data = {'x' : selected_count_x,
            'y' : selected_count_y,
            'intensity': SelectedLevel}      # was ThreadLevel
        #create a ColumnDataSource by passing the dict

        heat_source = ColumnDataSource(data=heatmap_data)
            
        latest = ContainerX[0][-1] + step
        for i in range(len(ContainerY)):
            ContainerY[i].append(ThreadLevel[i])
            ContainerY[i].pop(0)        # All values change equally

        ContainerX[0].append(latest)
        ContainerX[0].pop(0)        # All values change equally

        new_data_liveLine = {'xs' : ContainerX,
            'ys' : ContainerY,
            'line_color' : colours}

        liveLine_ds.data = new_data_liveLine
        mapper = linear_cmap(field_name="intensity", palette=colors, low=5000, high=25000)
        heatmap.rect(x='x',  y='y', width = 1, height = 1, source = heat_source, fill_color=mapper, line_color = "grey")

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

# Setup
curdoc().add_root(liveLine)
curdoc().add_root(heatmap)
curdoc().add_root(bar)
curdoc().add_root(layout)
curdoc().add_root(table)

button = Button(label="Stop/Resume", name = "button")
button.on_click(stopper)
curdoc().add_root(button)

menu = Dropdown(label = "Select Hierarchy", menu = ["BOX", "BOARD", "MAILBOX", "CORE"], name = "menu")
menu.on_click(clicker)
curdoc().add_root(menu)

curdoc().title = "POETS Dashboard"
curdoc().template_variables['stats_names'] = [ 'Threads', 'Cores', 'Refresh']
curdoc().template_variables['stats'] = {
    'Threads'     : {'icon': None,          'value': 49152,  'label': 'Total Threads'},
    'Cores'       : {'icon': None,        'value': 3072,  'label': 'Total Cores'},
    'Refresh'        : {'icon': None,        'value': refresh_rate,  'label': 'Refresh Rate'},
}
curdoc().add_periodic_callback(plotterUpdater, refresh_rate) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Ver
