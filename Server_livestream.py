import os
import sys
import socket
import threading
from random import randint
from LiveStream import LiveStreamVideo, LiveStreamAudio
from RtpPacket import RtpPacket

import time

class ServerWorker:
    def __init__(self, socket, clientAddr, live_stream_video, live_stream_audio):
        self.rtsp_socket = socket
        self.rtp_socket_video = None
        self.rtp_socket_audio = None
        self.rtp_addr = clientAddr[0]
        self.rtp_port_video = None
        self.rtp_port_audio = None
        self.state = 'INIT' # 'INIT', 'READY', PLAYING'
        self.live_stream_video = live_stream_video
        self.live_stream_audio = live_stream_audio
        self.session = None
        self.event = None
        self.worker_video = None
        self.worker_audio = None

        self.framNum_video = 0 # for aligning video and audio
        self.framNum_audio = 0

    def run(self):
        threading.Thread(target=self.receiveRTSPrequest).start()
    def receiveRTSPrequest(self):
        while True:
            data = self.rtsp_socket.recv(1024)
            if data:
                self.processRTSPrequest(data)
    def processRTSPrequest(self, data):
        print('### RTSP request received: {}'.format(data))
        request = data.decode().split('\n')
        requestType = request[0].split(' ')[0]
        seqNum = int(request[1])
        if requestType == 'SETUP':
            if self.state == 'INIT':
                print('SETUP request received')
                self.state = 'READY'
                self.session = randint(100000, 999999)
                self.rtp_port_video = int(request[2].split(' ')[-2])
                self.rtp_port_audio = int(request[2].split(' ')[-1])
                self.replyRTSP('OK_200', seqNum)
                
        elif requestType == 'PLAY':
            if self.state == 'READY':
                print('PLAY request received')
                self.state = 'PLAYING'
                self.rtp_socket_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.rtp_socket_audio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.event = threading.Event()
                # self.worker_video = threading.Thread(target=self.sendRTP_video)
                # self.worker_audio = threading.Thread(target=self.sendRTP_audio)
                self.worker = threading.Thread(target=self.sendRTP_video_and_audio)
                # self.worker_audio.start()
                # self.worker_video.start()
                self.worker.start()
                self.replyRTSP('OK_200', seqNum)
        elif requestType == 'PAUSE':
            if self.state == 'PLAYING':
                print('PAUSE request received')
                self.state = 'READY'
                self.event.set()
                self.replyRTSP('OK_200', seqNum)
        elif requestType == 'TEARDOWN':
            print('TEARDOWN request received')
            self.event.set()
            self.replyRTSP('OK_200', seqNum)
            self.rtp_socket_video.close()
        else:
            pass
    def sendRTP_video_and_audio(self):
        while  True:
            tot_start_time = time.time()
            if self.event.isSet():
                break
            # audio, delay 0.3 sec
            start_time=time.time()
            data = self.live_stream_audio.getNextChunk() # delay 0-0.008 sec
            framNum = self.live_stream_video.framNum
            self.rtp_socket_audio.sendto(self.makeRtpPacket(data, framNum), (self.rtp_addr, self.rtp_port_audio))
            end_time = time.time()
            print('Total Audio Delay: {}'.format(end_time-start_time))
            # video, delay 0.002
            for i in range(10):
                if self.event.isSet():
                    break
                start_time=time.time()
                data = self.live_stream_video.getNextFrame() # delay 0.002 sec
                framNum = self.live_stream_video.framNum
                self.framNum_video = framNum
                self.rtp_socket_video.sendto(self.makeRtpPacket(data, framNum), (self.rtp_addr, self.rtp_port_video))
                end_time = time.time()
                print('Total Video Delay: {}'.format(end_time-start_time))
            tot_end_time = time.time()
            print('Total 10 frame delay: {} ({})'.format(tot_end_time-tot_start_time, tot_end_time-tot_start_time-1/3))


    def sendRTP_video(self):
        
        while True:
            if self.event.isSet(): # PAUSE, TEARDOWN
                break
            self.event.wait(1/30-0.002-0.014+0.005)
            data = self.live_stream_video.getNextFrame()
            framNum = self.live_stream_video.framNum
            self.framNum_video = framNum
            self.rtp_socket_video.sendto(self.makeRtpPacket(data, framNum), (self.rtp_addr, self.rtp_port_video))
    def sendRTP_audio(self):
        while True:
            if self.event.isSet(): # PAUSE, TEARDOWN
                break
            # self.event.wait()
            data = self.live_stream_audio.getNextChunk()
            framNum = self.live_stream_video.framNum
            self.rtp_socket_audio.sendto(self.makeRtpPacket(data, framNum), (self.rtp_addr, self.rtp_port_audio))

    def makeRtpPacket(self, payload, framNum):
        rtpPacket = RtpPacket()
        rtpPacket.encode(framNum, payload)
        return rtpPacket.getPacket()
    
    def replyRTSP(self, code, seqNum):
        if code == 'OK_200':
            reply = 'RTSP/1.0 200 OK\nCSeq: {}\nSession: {}'.format(seqNum, self.session).encode()
            self.rtsp_socket.send(reply)

if __name__ == '__main__':

    HOST, PORT = '127.0.0.1', 8888
    rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # RTSP: TCP socket
    rtsp_socket.bind((HOST, PORT))

    # to avoid delay, open live stream before listening
    live_stream_video = LiveStreamVideo()
    live_stream_audio = LiveStreamAudio()

    print('RTSP socket listening...')
    rtsp_socket.listen(5)
    while True:
        rtsp_client, addr = rtsp_socket.accept()   # this accept {SockID,tuple object},tuple object = {clinet_addr,intNum}!!!
        ServerWorker(rtsp_client, addr, live_stream_video, live_stream_audio).run()

