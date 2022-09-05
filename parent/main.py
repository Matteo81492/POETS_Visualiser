''' This file generates a dashboard that includes a live heatmap and a multiline chart of the 
    POETS data that is received through the socket. At the bottom of the dashboard a bar chart
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
                          LinearColorMapper, PrintfTickFormatter, HoverTool,
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
PORT = 5064
#host = socket.gethostname()
#SERVER = socket.getaddrinfo(host, PORT, socket.AF_INET6)    ## Automatically get local IPV6 Address 
ADDR = ("::1", PORT)  ## local address for now
sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_IP) ## Create UDP socket
sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, False)
sock.bind(ADDR)
sock.settimeout(7)
disconnect_msg = "DISCONNECT"


# POETS Configurations
############################################################################
refresh_rate = 900 ## Time in millisecond for updating live plots
ThreadCount = 49152   # The actual number of threads present in a POETS box is 6144 - 49152 in total
ThreadLevel = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)
mainQueue = Queue()
mainQueue.put(ThreadLevel, False) ## initialise queue object so it isn't empty at start
current_data = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)
empty = np.ndarray(ThreadCount, buffer=np.zeros(ThreadCount), dtype=np.uint16)

n = 16 # number of threads in a core
root_core = 48 
root_mailbox = 24 
root_board = 6 
root_box = 2 

maxRow = 0 # This is the number of time instances needed to plot the thread data
entered = 0
total = 0

#### FPGA coordinates list used to transform non contiguous addresses into contiguous ones
FPGA_coords = [0] * 47 # 48 entries because it supports 8 POETS box hence 48 working FPGAs



# Plot Configurations, calculating heatmap coordinates based on hierarchical view
############################################################################
row_x = [x for x in range(root_core)]
core_count_x = []
core_count_y = []
for i in range(root_core + 16): ## + 16 because sixteen extra rows are needed to reach 3072 mailbox count
    core_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_core)]
    core_count_y.extend(column_y)
CoreCount = len(core_count_x)


row_x = [x for x in range(root_mailbox)]
mailbox_count_x = []
mailbox_count_y = []
for i in range(root_mailbox + 8): ## + 8 because eight extra rows are needed to reach 768 mailbox count
    mailbox_count_x.extend(row_x)
    column_y = [i * 2 for x in range(root_mailbox)]
    mailbox_count_y.extend(column_y)
MailboxCount = len(mailbox_count_x)


row_x = [x for x in range(root_board)]
board_count_x = []
board_count_y = []
for i in range(root_board+2):     ## + 2 because two extra rows are needed to reach 48 board count
    board_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_board)]
    board_count_y.extend(column_y)
BoardCount = len(board_count_x)


row_x = [x for x in range(root_box)]
box_count_x = []
box_count_y = []
for i in range(root_box+2):     ## + 2 because two extra rows are needed to reach 8 box count
    box_count_x.extend(row_x)
    column_y = [i*2 for x in range(root_box)]
    box_count_y.extend(column_y)
BoxCount = len(box_count_x)

selected_count_x = core_count_x
selected_count_y = core_count_y

#Configurations for Heatmap - Used for TX/S values
#Extra tools available on the webpage
TOOLS="crosshair,pan,wheel_zoom,zoom_in,zoom_out,box_zoom,undo,redo,reset,tap,save,"

TOOLTIPS = [("core", "$index"),
            ("TX/s", "@intensity")]

#Set the default option for the Hovertool tooltips
hover=HoverTool(tooltips=TOOLTIPS)
heatmap = figure(width = 590, height = 600, tools=[hover, TOOLS], title="Heat Map",  name = "heatmap", toolbar_location="below")

heatmap.axis.visible = False
heatmap.grid.visible = False
heatmap.toolbar.logo = None

#Fixed heatmap colours, going from light green to dark red
colours = ["#75968f", "#a5bab7", "#c9d9d3", "#e2e2e2", "#dfccce", "#ddb7b1", "#cc7878", "#933b41", "#550b1d"]
max_colour = 1000   ## variable used to change colour range for different hierarchical views

bar_map = LinearColorMapper(palette = colours, low = 0, high = 1000 )#5 to 25k
color_bar = ColorBar(color_mapper=bar_map,
                ticker=SingleIntervalTicker(interval = 100),
                formatter=PrintfTickFormatter(format="%d"+" TX/s"))

heatmap.add_layout(color_bar, 'right')


#Configurations for Live Line Chart - Used for TX
TOOLTIPS2 = [("Core", "$index")]
hover2=HoverTool(tooltips=TOOLTIPS2)
liveLine = figure(height = 590, width = 720, tools=[hover2, TOOLS], title = "Live Instrumentation", name = "liveLine", toolbar_location="below", y_axis_location = "right")
liveLine.toolbar.logo = None
liveLine.x_range.follow="end"       ## Makes x axis follow the time value
liveLine.x_range.follow_interval = 30
liveLine.x_range.range_padding=0
liveLine.xaxis.formatter = PrintfTickFormatter(format="%ds")
liveLine.xaxis.ticker = SingleIntervalTicker(interval= 1)
liveLine.yaxis.formatter = PrintfTickFormatter(format="%d TX/s")

step = refresh_rate/1000 # Step for X axis
zero_list = [0] * 4
step_list = [i * step for i in range(4)]

### Containers used to store point coordiantes for multi-line plotting
ContainerX = np.empty((CoreCount,),  dtype = object)
ContainerY = np.empty((CoreCount,), dtype =  object)
line_colours = []
for i in range(len(ContainerY)): 
    ContainerY[i]=[0,0,0,0]
    ContainerX[i]=step_list 
    line_colours.append(random.choice(palette2))

### empty plot data, to be filled during live run
liveLineO = liveLine.multi_line(xs = [], ys= [], line_color = []) 
liveLine_ds = liveLineO.data_source
TOOLS="hover,crosshair,undo,redo,reset,tap,save,pan"


#Configurations for Line plot - Used for Cache Miss - Hit - WB values
TOOLTIPS = [("second", "$index"),
            ("value", "$y")]

line = figure(width = 700, title = "Line Graph", tools = TOOLS, tooltips = TOOLTIPS, height=300, toolbar_location="below",
    x_axis_type="datetime", x_axis_location="above", y_axis_type="log", y_range=(10**2, 10**9),
    background_fill_color="#efefef", x_range = (0, 30))
line.toolbar.logo = None
line.xaxis.formatter = PrintfTickFormatter(format="%ss")

Hit_line = line.line(x=[], y=[], legend="Cache Hit")
Miss_line = line.line(x=[], y=[], legend="Cache Miss", color = "red")
WB_line = line.line(x=[], y=[], legend="Cache WB", color = "green")

Hit_line_ds = Hit_line.data_source
Miss_line_ds = Miss_line.data_source
WB_line_ds = WB_line.data_source

#Separated figure for the range selector, which allows to zoom in a specific section of time
select = figure(width = 550, title="Drag the middle and edges of the selection box to change the range above",
            height=100, y_range=line.y_range,
            x_axis_type="datetime", y_axis_type=None,
        tools="", toolbar_location=None, background_fill_color="#efefef")
select.xaxis.formatter = PrintfTickFormatter(format="%ss")
select.ygrid.grid_line_color = None

selectO = select.line(x = [], y =[])
select_ds = selectO.data_source
layout = column(line, select, name="line")
range_tool_active = 0


#Configurations for Bar Chart - Used for CPUIDLE count
TOOLS="hover,crosshair,undo,redo,reset,tap,save, pan, zoom_in,zoom_out,"

TOOLTIPS = [("second", "$index"),
            ("percentage", "@top")]

bar = figure(height = 580, width = 500, title="Bar Chart", name = "bar",
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

## specified initial values in order to show graph even before application runs
initial = dict()
initial['x'] = [0]
initial['top'] = [0]
bar_ds.data = initial

## values used to calculate percentage of idle time
idle_divider1 = CoreCount*2100000 ## freq is 210 MHz
idle_divider2 = CoreCount/100


## Configuration for table showing post-run parameters
execution_array = [0] * 10
usage_array = [0] * 10
tdata = {'Application' : range(1,11),
            'Execution Time' : execution_array,
            'Average Utilisation': usage_array,}  
source = ColumnDataSource(data=tdata)
columns = [
    TableColumn(field="Application", title="Application"),
    TableColumn(field="Execution Time", title="Execetution Time (s)",
                formatter=StringFormatter(text_align="center")),
    TableColumn(field="Average Utilisation", title="Average Utilisation (TX/s)",
                formatter=NumberFormatter(text_align="right")),
]
table = DataTable(source=source, columns=columns, height=150, width=700, name="table", sizing_mode="scale_both")

table_ds = table.source


finished = 0 # Variable used to indicate end of run
block = 0 # Variable used to freeze the Heatmap
gap1 = 16
gap2 = CoreCount
clear = 0
x_c = 1
final_plot = 0


def signal_handler(*args, **kwargs):
    print("\nTerminating Visualiser...")
    sock.close()
    print(f"active  {threading.active_count()}")
    sys.exit(0)


def stopper():
    global block
    print("STOPPING live updates")
    block = ~block

def clicker_h(event):
    global gap1, selected_count_x, selected_count_y, max_colour
    print(event.item + str(" VIEW FOR LIVE HEATMAP"))
    heatmap.renderers = []

    if event.item == "CORE":
        gap1 = 16
        selected_count_x = core_count_x
        selected_count_y = core_count_y
        max_colour = 1000
        heatmap.tools[0].tooltips = [("core", "$index"),
                                    ("TX/s", "@intensity")]
                            
    elif event.item == "MAILBOX":
        gap1 = 64
        selected_count_x = mailbox_count_x
        selected_count_y = mailbox_count_y
        max_colour = 500
        heatmap.tools[0].tooltips = [("mailbox", "$index"),
                                    ("TX/s", "@intensity")]
                                    
    elif event.item == "BOARD":
        gap1 = 1024
        selected_count_x = board_count_x
        selected_count_y = board_count_y
        max_colour = 200
        heatmap.tools[0].tooltips = [("board", "$index"),
                                    ("TX/s", "@intensity")]
    else:
        gap1 = 6144
        selected_count_x = box_count_x
        selected_count_y = box_count_y
        max_colour = 100
        heatmap.tools[0].tooltips = [("box", "$index"),
                                    ("TX/s", "@intensity")]

    mainQueue.put(empty)

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
            line_colours.append(random.choice(palette2)) 
        gap2 = CoreCount
        liveLine.tools[0].tooltips = [("core", "$index")]

    elif event.item == "THREAD":
        ContainerX = np.empty((ThreadCount,),  dtype = object)
        ContainerY = np.empty((ThreadCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2))
        gap2 = ThreadCount
        liveLine.tools[0].tooltips = [("thread", "$index")]

    elif event.item == "MAILBOX":
        ContainerX = np.empty((MailboxCount,),  dtype = object)
        ContainerY = np.empty((MailboxCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2))
        gap2 = MailboxCount
        liveLine.tools[0].tooltips = [("mailbox", "$index")]
                                    
    elif event.item == "BOARD":
        ContainerX = np.empty((BoardCount,),  dtype = object)
        ContainerY = np.empty((BoardCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2))
        gap2 = BoardCount
        liveLine.tools[0].tooltips = [("board", "$index")]

    else:
        ContainerX = np.empty((BoxCount,),  dtype = object)
        ContainerY = np.empty((BoxCount,), dtype =  object)
        line_colours = []
        for i in range(len(ContainerY)): 
            ContainerY[i]=[0,0,0,0]
            ContainerX[i]=step_list 
            line_colours.append(random.choice(palette2))
        gap2 = BoxCount
        liveLine.tools[0].tooltips = [("box", "$index")]

    mainQueue.put(empty)




def dataUpdater():
    print(" IN DATA UPDATER ")
    global ThreadLevel, cacheDataMiss1, cacheDataHit1, cacheDataWB1, CPUIdle1, finished, maxRow, entered, plot, counter1, clear, biggest, final_plot, clear_column
    idx = 0
    counter1 = 0
    cacheDataMiss1 = 0
    cacheDataHit1 = 0
    cacheDataWB1 = 0
    CPUIdle1 = 0
    counter = [0] * 10 
    cacheDataMiss = [0] * 10
    cacheDataHit = [0] * 10
    cacheDataWB = [0] * 10
    CPUIdle = [0] * 10
    plot = 0
    group = 0
    biggest = 1
    mask1 = 0b0000001111111111 
    final_plot
    f = 1
    clear_column = 0
 
    while True:
        try:
            data, address = sock.recvfrom(65535)   
            msg = data.decode("utf-8")
            if(clear):
                maxRow = 0
                clear_column = 1
                clear = 0

            entered = 1
            splitMsg = msg.split(API_DELIMINATOR)
            idx = int(float(splitMsg[0]))

            ############ FPGA field corresponds to the six MSB bits of the thread address, the following conversion makes the address range contiguous

            FPGA_field = bin(idx)[2:-10]
            if(FPGA_field):            ## IF FPGA FIELD IS DIFFERENT THAN ZERO AND IT EXISTS DO CONVERSION
                if FPGA_field in FPGA_coords:
                    new_field = FPGA_coords.index(FPGA_field) + 1
                    mask2 = (new_field << 10)
                else:
                    FPGA_coords[f] = FPGA_field
                    print(str(f) + " FPGA boards active")
                    f = (f+1)%47
                    mask2 = (f << 10)
                idx = (idx & mask1) | mask2

            if(idx > biggest):
                biggest = idx
            cidx = int(float(splitMsg[1]))
            if idx < ThreadCount and idx >= 0:
                ThreadLevel[idx] = int(float(splitMsg[7]))                   
                div = int(idx/n)
                if not idx%n and div < CoreCount:        ## Take only Thread 0 of each core as a representative of the entire core counter
                    if(maxRow < cidx):       
                        maxRow = cidx
                        group += 1
                    
                    if(group == 10):                    ## After every ten seconds of data refresh counters
                        group = 0
                        plot += 1                      
                        CPUIdle1 = CPUIdle + []
                        CPUIdle = [0] * 10
                        cacheDataMiss1 = cacheDataMiss + []
                        cacheDataMiss = [0] * 10
                        cacheDataHit1 = cacheDataHit + []
                        cacheDataHit = [0] * 10
                        cacheDataWB1 = cacheDataWB + []
                        cacheDataWB = [0] * 10
                        counter1 = counter + []
                        counter = [0] * 10

                    cacheDataMiss[group] += (int(float(splitMsg[3])))
                    cacheDataHit[group] += (int(float(splitMsg[4])))
                    cacheDataWB[group] += (int(float(splitMsg[5])))
                    CPUIdle[group] += int((float(splitMsg[6])))
                    counter[group] += 1
            else:
                print("idx range is out of bound")
        except socket.timeout:
            if(entered):
                group = 0
                final_plot = 10 - (maxRow%10)
                CPUIdle1 = CPUIdle + []
                CPUIdle = [0] * 10
                cacheDataMiss1 = cacheDataMiss + []
                cacheDataMiss = [0] * 10
                cacheDataHit1 = cacheDataHit + []
                cacheDataHit = [0] * 10
                cacheDataWB1 = cacheDataWB + []
                cacheDataWB = [0] * 10
                counter1 = counter + []
                counter = [0] * 10            
                print(disconnect_msg)
                finished = 1      ##after finishing the run display table data
                entered = 0
        except Exception as e:
            print("issue on thread " + str(idx) + " because: " + str(e))

def bufferUpdater():
    global mainQueue, total
    while True:
        if(entered) and not ((ThreadLevel==current_data).all()):        ## Queue new data in order to avoid losing it in case of slow rendering
            mainQueue.put(ThreadLevel, False)
            for e in range(biggest+1):
                total += np.sum(ThreadLevel[e])
        time.sleep(0.9)

def plotterUpdater():
    global finished, usage, range_tool_active, current_data, plot, total, clear, x_c, execution_array, usage_array, final_plot, clear_column

    if not(block):    
        if not (mainQueue.empty()):
            
            current_data = mainQueue.get()
            print(mainQueue.qsize())

            if(gap1 == 16):                     ## CORE VIEW
                HeatmapLevel = [sum(current_data[j:j+n])//n for j in range(0, biggest +1 ,n)]

            elif(gap1 == 64):                   ## MAILBOX VIEW
                HeatmapLevel = [sum(current_data[j:j+gap1])//gap1 for j in range(0, biggest + 1, gap1)]

            elif(gap1 == 1024):                 ## BOARD VIEW
                HeatmapLevel = [sum(current_data[j:j+gap1])//gap1 for j in range(0, biggest + 1 , gap1)]

            else:                               ## BOX VIEW
                HeatmapLevel = [sum(current_data[j:j+biggest])//gap1 for j in range(0, biggest + 1, biggest)]

            if(gap2 == CoreCount):              ## CORE VIEW 
                if(gap1 == 16):
                    LineLevel = HeatmapLevel
                else:
                    LineLevel = [sum(current_data[j:j+n])//n for j in range(0, biggest + 1 ,n)]
            
            elif(gap2 == MailboxCount):         ## MAILBOX VIEW 
                if(gap1 == 64):
                    LineLevel = HeatmapLevel
                else:
                    LineLevel = [sum(current_data[j:j+64])//64 for j in range(0, biggest + 1 ,64)]

            elif(gap2 == ThreadCount):          ## THREAD VIEW
                LineLevel = ThreadLevel[0:biggest+1]

            elif(gap2 == BoardCount):           ## BOARD VIEW 
                if(gap1 == 1024):
                    LineLevel = HeatmapLevel
                else:
                    LineLevel = [sum(current_data[j:j+1024])//1024 for j in range(0, biggest + 1 ,1024)]
            
            else:
                if(gap1 == 6144):               ## BOX VIEW 
                    LineLevel = HeatmapLevel
                else:
                    LineLevel = [sum(current_data[j:j+6144])//6144 for j in range(0, biggest + 1,6144)]



            heatmap_data = {'x' : selected_count_x,
                'y' : selected_count_y,
                'intensity': HeatmapLevel + [0] * (len(selected_count_x) - len(HeatmapLevel))}  ## Missing tiles are automatically set to zero intensity

            #create a ColumnDataSource by passing the dict
            heat_source = ColumnDataSource(data=heatmap_data)
            latest = ContainerX[0][-1] + step
            l = len(LineLevel)
            for i in range(l):
                ContainerY[i].append(LineLevel[i])
                ContainerY[i].pop(0)        

            ContainerX[0].append(latest)
            ContainerX[0].pop(0)        # All X values change equally since ContainerX arrays are all connected
            new_data_liveLine = {'xs' : ContainerX,
                'ys' : ContainerY,
                'line_color' : line_colours }

            liveLine_ds.data = new_data_liveLine
            mapper = linear_cmap(field_name="intensity", palette=colours, low=0, high= max_colour )
            heatmap.rect(x='x',  y='y', width = 1, height = 2, source = heat_source, fill_color=mapper, line_color = "grey")


        if(plot) or (final_plot):

            dataBar = dict()
            dataBar['x'] = bar_ds.data['x'] + [x_c] + [x_c+1] + [x_c+2] + [x_c+3] + [x_c+4] + [x_c+5] + [x_c+6] + [x_c+7] + [x_c+8] + [x_c+9]
            dataBar['top'] = bar_ds.data['top'] + [(CPUIdle1[0]/idle_divider1 + (CoreCount-counter1[0])/idle_divider2)] + [(CPUIdle1[1]/idle_divider1 + (CoreCount-counter1[1])/idle_divider2)] + [(CPUIdle1[2]/idle_divider1 + (CoreCount-counter1[2])/idle_divider2)] + [(CPUIdle1[3]/idle_divider1 + (CoreCount-counter1[3])/idle_divider2)] + [(CPUIdle1[4]/idle_divider1 + (CoreCount-counter1[4])/idle_divider2)] + [(CPUIdle1[5]/idle_divider1 + (CoreCount-counter1[5])/idle_divider2)] + [(CPUIdle1[6]/idle_divider1 + (CoreCount-counter1[6])/idle_divider2)] + [(CPUIdle1[7]/idle_divider1 + (CoreCount-counter1[7])/idle_divider2)] + [(CPUIdle1[8]/idle_divider1 + (CoreCount-counter1[8])/idle_divider2)] + [(CPUIdle1[9]/idle_divider1 + (CoreCount-counter1[9])/idle_divider2)]
            
            dataMiss = dict()
            dataMiss['x'] = Miss_line_ds.data['x'] + [x_c] + [x_c+1] + [x_c+2] + [x_c+3] + [x_c+4] + [x_c+5] + [x_c+6] + [x_c+7] + [x_c+8] + [x_c+9]
            dataMiss['y'] = Miss_line_ds.data['y'] + [(cacheDataMiss1[0]/CoreCount)] + [(cacheDataMiss1[1]/CoreCount)] + [(cacheDataMiss1[2]/CoreCount)]  + [(cacheDataMiss1[3]/CoreCount)] + [(cacheDataMiss1[4]/CoreCount)] + [(cacheDataMiss1[5]/CoreCount)] + [(cacheDataMiss1[6]/CoreCount)] + [(cacheDataMiss1[7]/CoreCount)]  + [(cacheDataMiss1[8]/CoreCount)] + [(cacheDataMiss1[9]/CoreCount)]

            dataHit = dict()
            dataHit['x'] = Hit_line_ds.data['x'] +[x_c] + [x_c+1] + [x_c+2] + [x_c+3] + [x_c+4] + [x_c+5] + [x_c+6] + [x_c+7] + [x_c+8] + [x_c+9]
            dataHit['y'] = Hit_line_ds.data['y'] + [(cacheDataHit1[0]/CoreCount)] + [(cacheDataHit1[1]/CoreCount)] + [(cacheDataHit1[2]/CoreCount)] + [(cacheDataHit1[3]/CoreCount)] + [(cacheDataHit1[4]/CoreCount)] + [(cacheDataHit1[5]/CoreCount)] + [(cacheDataHit1[6]/CoreCount)] + [(cacheDataHit1[7]/CoreCount)] + [(cacheDataHit1[8]/CoreCount)] + [(cacheDataHit1[9]/CoreCount)]

            dataWB = dict()
            dataWB['x'] = WB_line_ds.data['x'] + [x_c] + [x_c+1] + [x_c+2] + [x_c+3] + [x_c+4] + [x_c+5] + [x_c+6] + [x_c+7] + [x_c+8] + [x_c+9]
            dataWB['y'] = WB_line_ds.data['y'] + [(cacheDataWB1[0]/CoreCount)] + [(cacheDataWB1[1]/CoreCount)] + [(cacheDataWB1[2]/CoreCount)] + [(cacheDataWB1[3]/CoreCount)] + [(cacheDataWB1[4]/CoreCount)] + [(cacheDataWB1[5]/CoreCount)] + [(cacheDataWB1[6]/CoreCount)] + [(cacheDataWB1[7]/CoreCount)] + [(cacheDataWB1[8]/CoreCount)] + [(cacheDataWB1[9]/CoreCount)]


            x_c += 10

            if(final_plot) and not (plot):
                x_c = 1
                dataBar['x'] = dataBar['x'][:-final_plot]
                dataBar['top'] = dataBar['top'][:-final_plot]
                dataMiss['x'] = dataMiss['x'][:-final_plot]
                dataMiss['y'] = dataMiss['y'][:-final_plot]
                dataHit['x'] = dataHit['x'][:-final_plot]
                dataHit['y'] = dataHit['y'][:-final_plot]
                dataWB['x'] = dataWB['x'][:-final_plot]
                dataWB['y'] = dataWB['y'][:-final_plot]
                final_plot = 0

            else:
                plot -= 1          

            bar_ds.data = dataBar
            Miss_line_ds.data = dataMiss
            Hit_line_ds.data = dataHit
            WB_line_ds.data = dataWB
            select_ds.data = dataWB

        if(clear_column):
            Miss_line_ds.data['x'] = []
            Miss_line_ds.data['y'] = []
            Hit_line_ds.data['x'] = []
            Hit_line_ds.data['y'] = []  
            WB_line_ds.data['x'] = []
            WB_line_ds.data['y'] = []           
            bar_ds.data['x'] = []
            bar_ds.data['top'] = []
            clear_column = 0

        if(finished) and (mainQueue.empty()):
            print(" RENDERING OTHER GRAPHS ")           
            execution_array = np.roll(execution_array,1)
            execution_array[0] = maxRow
            usage_array = np.roll(usage_array, 1)
            usage_array[0] = round(total/execution_array[0], 3)
            newTable = {'Application' : table_ds.data['Application'],
                    'Execution Time'   : execution_array,
                    'Average Utilisation' : usage_array}
            table_ds.data = newTable

            print("REFRESHING")
            ####### REFRESHING
            mainQueue.put(empty, False) ## Add three void data sets to space application runs
            mainQueue.put(empty, False) 
            mainQueue.put(empty, False) 


            range_tool = RangeTool(x_range = line.x_range)
            range_tool.overlay.fill_color = "navy"
            range_tool.overlay.fill_alpha = 0.2
            if(range_tool_active == 0):
                select.add_tools(range_tool)
                select.toolbar.active_multi = range_tool
                range_tool_active = 1
            clear = 1
            total = 0
            finished = 0


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

# Buffer thread for the Queue object
bufferThread = threading.Thread(name='buffer',target=bufferUpdater)
bufferThread.daemon = True
bufferThread.start()

# Adding the plots to the current document
curdoc().add_root(liveLine)
curdoc().add_root(heatmap)
curdoc().add_root(bar)
curdoc().add_root(layout)
curdoc().add_root(table)

# Button Object
button = Button(label="Stop/Resume", name = "button", default_size = 150)
button.on_click(stopper)
curdoc().add_root(button)

# Dropdown list for the Heatmap
menu_h = Dropdown(label = "Select Hierarchy", menu = ["BOX", "BOARD", "MAILBOX", "CORE"], name = "menu_h")
menu_h.on_click(clicker_h)
curdoc().add_root(menu_h)

# Dropdown list for the Live Line plot
menu_l = Dropdown(label = "Select Hierarchy", menu = ["BOX", "BOARD", "MAILBOX", "CORE", "THREAD"], name = "menu_l")
menu_l.on_click(clicker_l)
curdoc().add_root(menu_l)

curdoc().title = "POETS Dashboard"

# Some system parameters to display on the webpage
curdoc().template_variables['stats_names'] = [ 'Threads', 'Cores', 'Refresh']
curdoc().template_variables['stats'] = {
    'Threads'     : {'icon': None,          'value': 49152,  'label': 'Total Threads'},
    'Cores'       : {'icon': None,        'value': 3072,  'label': 'Total Cores'},
    'Refresh'        : {'icon': None,        'value': refresh_rate,  'label': 'Refresh Rate (ms)'},
}

# PlotterUpdater is the callback function for the current document
curdoc().add_periodic_callback(plotterUpdater, refresh_rate) 
