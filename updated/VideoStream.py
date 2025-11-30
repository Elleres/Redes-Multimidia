class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, "rb")
        except:
            raise IOError("Não foi possível abrir o arquivo de vídeo.")
        self.frameNum = 0

    def nextFrame(self):
        """Get next frame."""
        data = self.file.read(5)  # framelength (first 5 bytes)
        if data:
            try:
                framelength = int(data)
            except:
                return None

            # Read the current frame
            data = self.file.read(framelength)
            self.frameNum += 1
            return data
        else:
            return None

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum
