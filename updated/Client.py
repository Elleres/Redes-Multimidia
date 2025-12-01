import os
import socket
import sys
import threading
from tkinter import *
from tkinter import messagebox
from PIL import Image, ImageTk
from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4  # Novo comando

    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0

    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        self.setup = Button(self.master, width=15, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=15, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=15, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=15, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)
        
        # Create Describe button (NOVO)
        self.describe = Button(self.master, width=15, padx=3, pady=3)
        self.describe["text"] = "Describe"
        self.describe["command"] = self.describeMovie
        self.describe.grid(row=1, column=4, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=5, sticky=W+E+N+S, padx=5, pady=5)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()
        try:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
        except OSError:
            pass

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            self.playEvent = threading.Event()
            self.playEvent.clear()
            threading.Thread(target=self.listenRtp, daemon=True).start()
            self.sendRtspRequest(self.PLAY)

    def describeMovie(self):
        """Describe button handler."""
        self.sendRtspRequest(self.DESCRIBE)

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)
                    currFrameNbr = rtpPacket.seqNum()
                    if currFrameNbr > self.frameNbr:
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
            except:
                if hasattr(self, "playEvent") and self.playEvent.is_set():
                    break
                if self.teardownAcked == 1:
                    try:
                        self.rtpSocket.shutdown(socket.SHUT_RDWR)
                        self.rtpSocket.close()
                    except:
                        pass
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=288)
        self.label.image = photo

    def connectToServer(self):
        """Connect to the Server."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            messagebox.showwarning("Connection Failed", "Connection to '%s' failed." % self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        self.rtspSeq += 1
        
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply, daemon=True).start()
            request = "SETUP {} RTSP/1.0\nCSeq: {}\nTransport: RTP/UDP; client_port= {}\n".format(self.fileName, self.rtspSeq, self.rtpPort)
            self.requestSent = self.SETUP
        
        elif requestCode == self.PLAY and self.state == self.READY:
            request = "PLAY {} RTSP/1.0\nCSeq: {}\nSession: {}\n".format(self.fileName, self.rtspSeq, self.sessionId)
            self.requestSent = self.PLAY
        
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            request = "PAUSE {} RTSP/1.0\nCSeq: {}\nSession: {}\n".format(self.fileName, self.rtspSeq, self.sessionId)
            self.requestSent = self.PAUSE
        
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            request = "TEARDOWN {} RTSP/1.0\nCSeq: {}\nSession: {}\n".format(self.fileName, self.rtspSeq, self.sessionId)
            self.requestSent = self.TEARDOWN
            
        elif requestCode == self.DESCRIBE:
            # Se for chamado antes do Setup, precisamos garantir que a thread de resposta esteja rodando
            if self.state == self.INIT:
                 threading.Thread(target=self.recvRtspReply, daemon=True).start()
            request = "DESCRIBE {} RTSP/1.0\nCSeq: {}\nSession: {}\n".format(self.fileName, self.rtspSeq, self.sessionId)
            self.requestSent = self.DESCRIBE
            
        else:
            return

        try:
            self.rtspSocket.send(request.encode("utf-8"))
            print("\nData sent:\n" + request)
        except Exception as e:
            print("Failed sending RTSP request:", e)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            try:
                reply = self.rtspSocket.recv(4096)
                if reply:
                    self.parseRtspReply(reply.decode("utf-8"))
                
                if self.requestSent == self.TEARDOWN:
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                    self.rtspSocket.close()
                    break
            except:
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        lines = data.splitlines()
        if not lines: return

        try:
            seqNum = int(lines[1].split(" ")[1])
        except:
            return

        if seqNum == self.rtspSeq:
            try:
                session = int(lines[2].split(" ")[1])
            except:
                session = self.sessionId

            if self.sessionId == 0: self.sessionId = session
            
            if self.sessionId == session:
                if int(lines[0].split(" ")[1]) == 200:
                    if self.requestSent == self.SETUP:
                        self.state = self.READY
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        if hasattr(self, "playEvent"): self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        self.state = self.INIT
                        self.teardownAcked = 1
                    elif self.requestSent == self.DESCRIBE:
                        # Extrai o corpo SDP e mostra no terminal
                        body = ""
                        if "\n\n" in data:
                            body = data.split("\n\n", 1)[1]
                        elif "\r\n\r\n" in data:
                            body = data.split("\r\n\r\n", 1)[1]
                        else:
                            if "v=0" in data:
                                body = data[data.find("v=0"):]
                            else:
                                body = "No SDP body found"
                                
                        print(body.strip())

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.settimeout(0.5)
        try:
            self.rtpSocket.bind(("", self.rtpPort))
        except:
            messagebox.showwarning("Unable to Bind", "Unable to bind PORT=%d" % self.rtpPort)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playMovie()