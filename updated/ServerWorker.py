import socket
import sys
import threading
import traceback
from random import randint

from RtpPacket import RtpPacket
from VideoStream import VideoStream


class ServerWorker:
    SETUP = "SETUP"
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    TEARDOWN = "TEARDOWN"

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
            data = connSocket.recv(256)
            if data:
                # Decode bytes → string
                data = data.decode()
                print("Data received:\n" + data)
                self.processRtspRequest(data)

    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Split request lines
        request = data.split("\n")

        # First line: "SETUP filename RTSP/1.0"
        line1 = request[0].split(" ")
        requestType = line1[0]
        filename = line1[1]

        # Second line: "CSeq: X"
        seq = request[1].split(" ")

        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP\n")

                try:
                    self.clientInfo["videoStream"] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    return

                # Random session ID
                self.clientInfo["session"] = randint(100000, 999999)

                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1])

                # Get RTP port from last line
                self.clientInfo["rtpPort"] = request[2].split(" ")[3]

        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING

                # Create RTP socket
                self.clientInfo["rtpSocket"] = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM
                )

                self.replyRtsp(self.OK_200, seq[1])

                # Start sending RTP packets
                self.clientInfo["event"] = threading.Event()
                self.clientInfo["worker"] = threading.Thread(target=self.sendRtp)
                self.clientInfo["worker"].start()

        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY

                self.clientInfo["event"].set()

                self.replyRtsp(self.OK_200, seq[1])

        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            self.clientInfo["event"].set()
            self.replyRtsp(self.OK_200, seq[1])

            # Close RTP socket
            try:
                self.clientInfo["rtpSocket"].close()
            except:
                pass

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

                    self.clientInfo["rtpSocket"].sendto(
                        self.makeRtp(data, frameNumber), (address, port)
                    )
                except Exception as e:
                    print("Connection Error:", e)

                    # traceback.print_exc()

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

        rtpPacket.encode(
            version, padding, extension, cc, seqnum, marker, pt, ssrc, payload
        )

        return rtpPacket.getPacket()

    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        connSocket = self.clientInfo["rtspSocket"][0]

        if code == self.OK_200:
            reply = (
                f"RTSP/1.0 200 OK\nCSeq: {seq}\nSession: {self.clientInfo['session']}"
            )
            connSocket.send(reply.encode())

        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")

        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
