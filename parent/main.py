''' This file generates a dashboard that includes a live heatmap and multiline chart of the 
    POETS data that is received through the socket. After the application run is over, a bar chart
    and a line graph show idle and cache values respectively. The dashboard follows a Bootstrap
    template and is shown locally.
'''
from multiprocessing import Queue
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
ADDR = ("::1", PORT)
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_IP) ## Create UDP socket
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)
sock.bind(ADDR)
sock.settimeout(5)
disconnect_msg = "DISCONNECT"
mainQueue = Queue()

# POETS Configurations
############################################################################
refresh_rate = 1000 ## Time in millisecond for updating live plots
ThreadCount = 49152   # The actual number of threads present in a POETS box is 6144 - 49152 in total
ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)
mainQueue.put(ThreadLevel, False) ## initialise queue object so it isn't empty at start
current_data = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)
n = 16 # number of threads in a core
root_core = int(math.sqrt(ThreadCount / n))
root_mailbox = int(math.sqrt(ThreadCount / 64))
root_board = int(math.sqrt(ThreadCount / 1024))
root_box = int(math.sqrt(ThreadCount / 6144))

CoreCount = root_core * root_core
maxRow = 0 # This is the number of time instances needed to plot the thread data
entered = 0
total = 0
execution_time = 0
usage = 0


# Plot Configurations
############################################################################
row_x = [x for x in range(root_core)] #To define central square coordinates, a 0.5 offset is needed
core_count_x = []
core_count_y = []
for i in range(root_core):
    core_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_core)]
    core_count_y.extend(column_y)
len_core = len(core_count_x) * 16



row_x = [x for x in range(root_mailbox)]
mailbox_count_x = []
mailbox_count_y = []
for i in range(root_mailbox):
    mailbox_count_x.extend(row_x)
    column_y = [i * 2 for x in range(root_mailbox)]
    mailbox_count_y.extend(column_y)
len_mailbox = len(mailbox_count_x) * 64


row_x = [x for x in range(root_board)]
board_count_x = []
board_count_y = []
for i in range(root_board+2):     ## + 2 because two extra rows are needed to reach 48 board count
    board_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_board)]
    board_count_y.extend(column_y)
len_board = len(board_count_x) * 1024


row_x = [x for x in range(root_box)]
box_count_x = []
box_count_y = []
for i in range(root_box+2):     ## + 2 because two extra rows are needed to reach 8 box count
    box_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_box)]
    box_count_y.extend(column_y)
len_box = len(box_count_x) * 6144

#Configurations for Heatmap - Used for TX/S values

#Extra tools available on the webpage
TOOLS="crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,"

TOOLTIPS = [("core", "$index"),
            ("TX/s", "@intensity")]

#Set the default option for the Hovertool tooltips
hover=HoverTool(tooltips=TOOLTIPS)
heatmap = figure(width = 560, height = 600, tools=[hover, TOOLS], title="Heat Map",  name = "heatmap", toolbar_location="below")

heatmap.axis.visible = False
heatmap.grid.visible = False
heatmap.toolbar.logo = None

#Fixed heatmap color, going from light green to dark red
colours = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
bar_map = LinearColorMapper(palette = colours, low = 5000, high = 25000 )
color_bar = ColorBar(color_mapper=bar_map,
                ticker=SingleIntervalTicker(interval = 2500),
                formatter=PrintfTickFormatter(format="%d"+" TX/s"))

heatmap.add_layout(color_bar, 'right')


#Configurations for Live Line Chart - Used for TX
TOOLTIPS2 = [("Core", "$index")]
hover2=HoverTool(tooltips=TOOLTIPS2)
liveLine = figure(height = 590, width = 720, tools=[hover2, TOOLS], title = "Live Instrumentation", name = "liveLine", toolbar_location="below", y_axis_location = "right")
liveLine.toolbar.logo = None
liveLine.x_range.follow="end"
liveLine.x_range.follow_interval = 30
liveLine.x_range.range_padding=0
liveLine.xaxis.formatter = PrintfTickFormatter(format="%ds")
liveLine.xaxis.ticker = SingleIntervalTicker(interval= 1)
liveLine.yaxis.formatter = PrintfTickFormatter(format="%d TX/s")

step = refresh_rate/1000 # Step for X range
zero_list = [0] * 5
step_list = [i * step for i in range(5)]

ContainerX = np.empty((CoreCount,),  dtype = object)
ContainerY = np.empty((CoreCount,), dtype =  object)
line_colours = []
for i in range(len(ContainerY)): 
    ContainerY[i]=[0,0,0,0,0]
    ContainerX[i]=step_list 
    line_colours.append(random.choice(palette2)) #### try to eliminate random


liveLineO = liveLine.multi_line(xs = [], ys= [], line_color = []) 
liveLine_ds = liveLineO.data_source

TOOLS="hover,crosshair,undo,redo,reset,tap,save,pan"

#Configurations for Line plot - Used for Cache Miss - Hit - WB values
TOOLTIPS = [("second", "$index"),
            ("value", "$y")]

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
TOOLS="hover,crosshair,undo,redo,reset,tap,save, pan, zoom_in,zoom_out,"

TOOLTIPS = [("second", "$index"),
            ("percentage", "@top")]

bar = figure(height = 580, width = 490, title="Bar Chart", name = "bar",
        toolbar_location="below", tools=TOOLS, tooltips = TOOLTIPS, y_range = (0, 100))
bar.toolbar.logo = None
bar.xgrid.grid_line_color = None
bar.axis.minor_tick_line_color = None
bar.outline_line_color = None
bar.yaxis.formatter = PrintfTickFormatter(format="%d%%")
bar.xaxis.formatter = PrintfTickFormatter(format="%ss")
bar.yaxis.ticker = SingleIntervalTicker(interval=10)
bar.xaxis.ticker = SingleIntervalTicker(interval= 10)

barO = bar.vbar(x=[], top = [], width=0.2, color="#718dbf")
bar_ds = barO.data_source



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

table_ds = table.source


finished = 0 # Variable used to start other graphs
block = 0 # Variable used to freeze the Heatmap
gap1 = 16
gap2 = 0
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

def clicker_h(event):
    global gap1
    print(event.item + str(" VIEW FOR LIVE HEATMAP"))
    heatmap.renderers = []

    if event.item == "CORE":
        gap1 = 16
        heatmap.tools[0].tooltips = [("core", "$index"),
                                    ("TX/s", "@intensity")]
                            
    elif event.item == "MAILBOX":
        gap1 = 64
        heatmap.tools[0].tooltips = [("mailbox", "$index"),
                                    ("TX/s", "@intensity")]
                                    
    elif event.item == "BOARD":
        gap1 = 1024
        heatmap.tools[0].tooltips = [("board", "$index"),
                                    ("TX/s", "@intensity")]
    else:
        gap1 = 6144
        heatmap.tools[0].tooltips = [("box", "$index"),
                                    ("TX/s", "@intensity")]

    mainQueue.put(ThreadLevel)

def clicker_l(event):
    global ContainerX, ContainerY, line_colours, gap2
    print(event.item + str(" VIEW FOR LIVE LINE"))

    if event.item == "CORE":
        ContainerX = np.empty((CoreCount,),  dtype = object)
        ContainerY = np.empty((CoreCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2)) #### try to eliminate random
        gap2 = 0
        liveLine.tools[0].tooltips = [("core", "$index")]

    elif event.item == "THREAD":
        ContainerX = np.empty((ThreadCount,),  dtype = object)
        ContainerY = np.empty((ThreadCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2)) #### try to eliminate random
        gap2 = 1
        liveLine.tools[0].tooltips = [("thread", "$index")]

    elif event.item == "MAILBOX":
        ContainerX = np.empty((len(mailbox_count_x,)),  dtype = object)
        ContainerY = np.empty((len(mailbox_count_y,)), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2)) #### try to eliminate random
        gap2 = 2
        liveLine.tools[0].tooltips = [("mailbox", "$index")]
                                    
    elif event.item == "BOARD":
        ContainerX = np.empty((len(board_count_x,)),  dtype = object)
        ContainerY = np.empty((len(board_count_y,)), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2)) #### try to eliminate random
        gap2 = 3
        liveLine.tools[0].tooltips = [("board", "$index")]

    else:
        ContainerX = np.empty((len(box_count_x,)),  dtype = object)
        ContainerY = np.empty((len(box_count_y,)), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2)) #### try to eliminate random
        gap2 = 4
        liveLine.tools[0].tooltips = [("box", "$index")]

    mainQueue.put(ThreadLevel)




def dataUpdater():
    print(" IN DATA UPDATER ")
    global ThreadLevel, cacheDataMiss1, cacheDataHit1, cacheDataWB1, CPUIdle1, finished, maxRow, entered, plot, counter1
    idx = 0
    counter1 = 0
    cacheDataMiss1 = 0
    cacheDataHit1 = 0
    cacheDataWB1 = 0
    CPUIdle1 = 0
    counter2 = 0
    cacheDataMiss2 = 0
    cacheDataHit2 = 0
    cacheDataWB2 = 0
    CPUIdle2 = 0
    plot = 0
    while True:
        try:
            data, address = sock.recvfrom(65535)    ## Potential Bottleneck, no parallel behaviour, look into network buffering
            msg = data.decode("utf-8")
            entered = 1
            splitMsg = msg.split(API_DELIMINATOR)
            idx = int(float(splitMsg[0]))
            cidx = int(float(splitMsg[1]))
            if idx < ThreadCount and idx >= 0:
                ThreadLevel[idx] = int(float(splitMsg[7]))                   
                div = int(idx/n)
                if not idx%n and div < CoreCount:        ## Take only Thread 0 of each core as a representative of the entire core counter
                    if(maxRow < cidx):       ## Count max number of rows, this determines Points to plot. Problem if fewer than 2 rows
                        maxRow = cidx
                        plot = 1
                        CPUIdle1 = CPUIdle2
                        CPUIdle2 = 0
                        cacheDataMiss1 = cacheDataMiss2
                        cacheDataMiss2 = 0
                        cacheDataHit1 = cacheDataHit2
                        cacheDataHit2 = 0
                        cacheDataWB1 = cacheDataWB2
                        cacheDataWB2 = 0
                        counter1 = CoreCount - counter2
                        counter2 = 0
                    cacheDataMiss2 += (int(float(splitMsg[3])))
                    cacheDataHit2 += (int(float(splitMsg[4])))
                    cacheDataWB2 += (int(float(splitMsg[5])))
                    CPUIdle2 += (int(float(splitMsg[6])))
                    counter2 += 1
            else:
                print("idx range is out of bound")
        except socket.timeout:
            if(entered):
                print(disconnect_msg)
                finished = 1      ##WHEN DISCONNECTION HAPPENS RUN OTHER GRAPHS
                entered = 0
        except Exception as e:
            print("issue on thread " + str(idx) + " because: " + str(e))

def bufferUpdater():
    global mainQueue, total
    while True:
        if(entered) and not ((ThreadLevel==current_data).all()):
            mainQueue.put(ThreadLevel, False)
            for e in range(len(ThreadLevel)):
                total += np.sum(ThreadLevel[e])
        time.sleep(0.9)

def plotterUpdater():
    global finished, cacheDataMiss, cacheDataHit, cacheDataWB, CPUIdle, maxRow, execution_time, usage, range_tool_active, current_data, plot

    
    if(finished) and (mainQueue.empty()):
        print(" RENDERING OTHER GRAPHS ")
        execution_time2 = execution_time
        usage2 = usage
        execution_time = maxRow + 1



        range_tool = RangeTool(x_range=line.x_range)
        range_tool.overlay.fill_color = "navy"
        range_tool.overlay.fill_alpha = 0.2

        if(range_tool_active == 0):
            select.add_tools(range_tool)
            select.toolbar.active_multi = range_tool

        range_tool_active = 1



        usage = round(total/execution_time, 3)
        newTable = {'Application' : table_ds.data['Application'],
                'Execution Time'   : [execution_time, execution_time2],
                'Average Utilisation' : [usage, usage2]}
        table_ds.data = newTable

        #######REFRESHING
        heatmap.renderers = []
        liveLine.renderers = []
        empty = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)
        mainQueue.put(empty, False) ## Re-initialise so that it is not empty and plotting can take place
        
        finished = 0

    if not (block) and not (mainQueue.empty()):
        
        current_data = mainQueue.get()
        print(mainQueue.qsize())

        if(gap1 == 16):                     ## CORE VIEW
            selected_count_x = core_count_x
            selected_count_y = core_count_y
            HeatmapLevel = [sum(current_data[j:j+n])//n for j in range(0, len_core ,n)]


        elif(gap1 == 64):                   ## MAILBOX VIEW
            selected_count_x = mailbox_count_x
            selected_count_y = mailbox_count_y
            HeatmapLevel = [sum(current_data[j:j+gap1])//gap1 for j in range(0, len_mailbox, gap1)]

        elif(gap1 == 1024):                 ## BOARD VIEW
            selected_count_x = board_count_x
            selected_count_y = board_count_y
            HeatmapLevel = [sum(current_data[j:j+gap1])//gap1 for j in range(0, len_board, gap1)]

        else:                               ## BOX VIEW
            selected_count_x = box_count_x
            selected_count_y = box_count_y
            HeatmapLevel = [sum(current_data[j:j+gap1])//gap1 for j in range(0, len_box, gap1)]

        if(gap2 == 0):                     ## CORE VIEW 
            if(gap1 == 16):
                LineLevel = HeatmapLevel
            else:
                LineLevel = [sum(current_data[j:j+n])//n for j in range(0, len_core ,n)]
        
        elif(gap2 == 2):                     ## MAILBOX VIEW 
            if(gap1 == 64):
                LineLevel = HeatmapLevel
            elif(gap1 == 16):
                LineLevel = [sum(HeatmapLevel[j:j+4])//4 for j in range(0, int(len_mailbox/16) ,4)]
            else:
                LineLevel = [sum(current_data[j:j+64])//64 for j in range(0, int(len_mailbox) ,64)]

        elif(gap2 == 1):                   ## THREAD VIEW
            LineLevel = ThreadLevel

        elif(gap2 == 3):                     ## BOARD VIEW 
            if(gap1 == 1024):
                LineLevel = HeatmapLevel
            elif(gap1 == 16):
                LineLevel = [sum(HeatmapLevel[j:j+64])//64 for j in range(0, int(len_board/16) ,64)]
            elif(gap1 == 64):
                LineLevel = [sum(HeatmapLevel[j:j+16])//16 for j in range(0, int(len_board/64) ,16)]
            else:
                LineLevel = [sum(current_data[j:j+1024])//1024 for j in range(0, int(len_board) ,1024)]
        
        else:
            if(gap1 == 6144):
                LineLevel = HeatmapLevel
            elif(gap1 == 16):
                LineLevel = [sum(HeatmapLevel[j:j+384])//384 for j in range(0, int(len_box/16) ,384)]
            elif(gap1 == 64):
                LineLevel = [sum(HeatmapLevel[j:j+96])//96 for j in range(0, int(len_box/64) ,96)]
            elif(gap1 == 1024):
                LineLevel = [sum(HeatmapLevel[j:j+6])//6 for j in range(0, int(len_box/1024) ,6)]
            else:
                LineLevel = [sum(current_data[j:j+6144])//6144 for j in range(0, int(len_box) ,6144)]



        heatmap_data = {'x' : selected_count_x,
            'y' : selected_count_y,
            'intensity': HeatmapLevel}      # was ThreadLevel
        #create a ColumnDataSource by passing the dict

        heat_source = ColumnDataSource(data=heatmap_data)
            
        latest = ContainerX[0][-1] + step
        for i in range(len(ContainerY)):
            ContainerY[i].append(LineLevel[i])
            ContainerY[i].pop(0)        # All values change equally

        ContainerX[0].append(latest)
        ContainerX[0].pop(0)        # All values change equally

        new_data_liveLine = {'xs' : ContainerX,
            'ys' : ContainerY,
            'line_color' : line_colours}

        liveLine_ds.data = new_data_liveLine
        mapper = linear_cmap(field_name="intensity", palette=colours, low=0, high=6000) ## was 5k - 25k
        heatmap.rect(x='x',  y='y', width = 1, height = 2, source = heat_source, fill_color=mapper, line_color = "grey")

    if(plot) and not (finished):
        plot = 0
        finalIdle = int((CPUIdle1 + (counter1*210000000))/(CoreCount*2100000))
        finalMiss = int(cacheDataMiss1/CoreCount)
        finalHit = int(cacheDataHit1/CoreCount)
        finalWB = int(cacheDataWB1/CoreCount)            

        dataBar = dict()
        dataBar['x'] = bar_ds.data['x'] + [maxRow]
        dataBar['top'] = bar_ds.data['top'] + [finalIdle]
        bar_ds.data = dataBar
        
        dataMiss = dict()
        dataMiss['x'] = Miss_line_ds.data['x'] + [maxRow]
        dataMiss['y'] = Miss_line_ds.data['y'] + [finalMiss]
        Miss_line_ds.data = dataMiss

        dataHit = dict()
        dataHit['x'] = Hit_line_ds.data['x'] + [maxRow]
        dataHit['y'] = Hit_line_ds.data['y'] + [finalHit]
        Hit_line_ds.data = dataHit

        dataWB = dict()
        dataWB['x'] = WB_line_ds.data['x'] + [maxRow]
        dataWB['y'] = WB_line_ds.data['y'] + [finalWB]
        WB_line_ds.data = dataWB

        select_ds.data = dataMiss


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

bufferThread = threading.Thread(name='buffer',target=bufferUpdater)
bufferThread.daemon = True
bufferThread.start()

# Setup
curdoc().add_root(liveLine)
curdoc().add_root(heatmap)
curdoc().add_root(bar)
curdoc().add_root(layout)
curdoc().add_root(table)


button = Button(label="Stop/Resume", name = "button", default_size = 150)
button.on_click(stopper)
curdoc().add_root(button)

menu_h = Dropdown(label = "Select Hierarchy", menu = ["BOX", "BOARD", "MAILBOX", "CORE"], name = "menu_h")
menu_h.on_click(clicker_h)
curdoc().add_root(menu_h)

menu_l = Dropdown(label = "Select Hierarchy", menu = ["BOX", "BOARD", "MAILBOX", "CORE", "THREAD"], name = "menu_l")
menu_l.on_click(clicker_l)
curdoc().add_root(menu_l)

curdoc().title = "POETS Dashboard"
curdoc().template_variables['stats_names'] = [ 'Threads', 'Cores', 'Refresh']
curdoc().template_variables['stats'] = {
    'Threads'     : {'icon': None,          'value': 49152,  'label': 'Total Threads'},
    'Cores'       : {'icon': None,        'value': 3072,  'label': 'Total Cores'},
    'Refresh'        : {'icon': None,        'value': refresh_rate,  'label': 'Refresh Rate'},
}
curdoc().add_periodic_callback(plotterUpdater, refresh_rate) # or processThread = threading.Thread(name='process',target=UpdateThread, args=(recQ,))Verz
