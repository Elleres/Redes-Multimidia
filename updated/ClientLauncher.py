import sys
from tkinter import Tk

from Client import Client

if __name__ == "__main__":
    try:
        serverAddr = sys.argv[1]
        serverPort = int(sys.argv[2])
        rtpPort = int(sys.argv[3])
        fileName = sys.argv[4]
    except IndexError:
        print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]")
        sys.exit(1)

    root = Tk()

    # Create a new client
    app = Client(root, serverAddr, serverPort, rtpPort, fileName)
    app.master.title("RTPClient")

    root.mainloop()
