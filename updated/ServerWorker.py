import socket
import sys
import threading
from random import randint
from RtpPacket import RtpPacket
from VideoStream import VideoStream

class ServerWorker:
    SETUP = "SETUP"
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    TEARDOWN = "TEARDOWN"
    DESCRIBE = "DESCRIBE"

    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    clientInfo = {}

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo["rtspSocket"][0]
        while True:
            try:
                data = connSocket.recv(256)
                if data:
                    print("Data received:\n" + data.decode())
                    self.processRtspRequest(data.decode())
                else:
                    break
            except:
                break

    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        request = data.split("\n")
        line1 = request[0].split(" ")
        requestType = line1[0]
        filename = line1[1]
        seq = request[1].split(" ")

        if requestType == self.SETUP:
            if self.state == self.INIT:
                try:
                    self.clientInfo["videoStream"] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    return
                self.clientInfo["session"] = randint(100000, 999999)
                self.replyRtsp(self.OK_200, seq[1])
                self.clientInfo["rtpPort"] = request[2].split(" ")[3]

        elif requestType == self.PLAY:
            if self.state == self.READY:
                self.state = self.PLAYING
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.replyRtsp(self.OK_200, seq[1])
                self.clientInfo["event"] = threading.Event()
                self.clientInfo["worker"] = threading.Thread(target=self.sendRtp)
                self.clientInfo["worker"].start()

        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                self.state = self.READY
                self.clientInfo["event"].set()
                self.replyRtsp(self.OK_200, seq[1])

        elif requestType == self.TEARDOWN:
            self.clientInfo["event"].set()
            self.replyRtsp(self.OK_200, seq[1])
            try:
                self.clientInfo["rtpSocket"].close()
            except:
                pass
        
        elif requestType == self.DESCRIBE:
            # Cria o corpo SDP (Session Description Protocol)
            sdp = "v=0\n"
            sdp += "o=- " + str(self.clientInfo.get('session', 0)) + " 1 IN IP4 127.0.0.1\n"
            sdp += "s=RTSP Session\n"
            sdp += "m=video " + str(self.clientInfo.get('rtpPort', '0')) + " RTP/AVP 26\n"
            sdp += "a=mimetype:string; \"video/MJPEG\"\n"
            
            self.replyRtsp(self.OK_200, seq[1], sdp)

    def sendRtp(self):
        """Send RTP packets over UDP."""
        while True:
            self.clientInfo["event"].wait(0.05)
            if self.clientInfo["event"].is_set():
                break
            data = self.clientInfo["videoStream"].nextFrame()
            if data:
                frameNumber = self.clientInfo["videoStream"].frameNbr()
                try:
                    address = self.clientInfo["rtspSocket"][1][0]
                    port = int(self.clientInfo["rtpPort"])
                    self.clientInfo["rtpSocket"].sendto(self.makeRtp(data, frameNumber), (address, port))
                except:
                    pass

    def makeRtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26
        seqnum = frameNbr
        ssrc = 0
        rtpPacket = RtpPacket()
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
        return rtpPacket.getPacket()

    def replyRtsp(self, code, seq, content=None):
        """Send RTSP reply to the client."""
        connSocket = self.clientInfo["rtspSocket"][0]
        if code == self.OK_200:
            reply = "RTSP/1.0 200 OK\nCSeq: {}\nSession: {}\n".format(seq, self.clientInfo.get('session', 0))
            if content:
                reply += "Content-Type: application/sdp\n"
                reply += "Content-Length: {}\n".format(len(content))
                reply += "\n" + content
            else:
                reply += "\n"
            connSocket.send(reply.encode())
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")