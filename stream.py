from imutils.video.pivideostream import PiVideoStream
from flask import Flask, render_template, Response, request
import time
import cv2

class SPiCamera(object):
    def __init__(self, flip=False):
        self.vs = PiVideoStream().start()
        self.flip = flip
        time.sleep(2.0)

    def __del__(self):
        self.vs.stop()

    def flip_if_needed(self,frame):
        if self.flip:
            return np.flip(frame,0)
        return frame

    def get_frame(self):
        frame = self.flip_if_needed(self.vs.read())
        t, jpeg = cv2.imencode('.jpg',frame)
        return jpeg.tobytes()


app = Flask(__name__)
cam = SPiCamera()

@app.route('/')
def index():
    return render_template('index.html') #you can customze index.html here

def gen(camera):
    #get camera frame
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(gen(cam),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


def start_flask_server():
    app.run(host='0.0.0.0', debug=False)