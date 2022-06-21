from multiprocessing import Process, Queue
import threading
import random
import sys
import os
import datetime
import time
import signal
import socket

visAddr = "127.0.0.1"
visPort = 9000
visSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

API_DELIMINATOR = "¿"

graphData = 0
message_str = ""
while True:
    start = time.time()
    for i in range(50):
        graphData = 13000 + ((random.random()-0.5)*((i%5)+1)*1000)
        message_str = str(i) + API_DELIMINATOR + str(graphData)
        visSock.sendto(message_str.encode('utf-8'), (visAddr, visPort))
    for i in range(51,63):
        graphData = 30000 + ((random.random()-0.5)*((i%5)+1)*1000)
        message_str = str(i) + API_DELIMINATOR + str(graphData)
        visSock.sendto(message_str.encode('utf-8'), (visAddr, visPort))
    duration = time.time() - start
    time.sleep(1-duration)