from picamera.array import PiRGBArray
from picamera import PiCamera
from warcram_utils import utils
import stream
import argparse
import warnings
import datetime
import imutils
import json
import time
import cv2
import math
import io
import threading
import dropbox
import subprocess
import os
import numpy as np




def sw_print(msg, err_level, config):
    utils.print_switch(msg, config["app_name"], err_level, config["verbose"])

def sanity_check():
    argParser = argparse.ArgumentParser()
    argParser.add_argument("-c","--conf", required=True, help="Path to json configuration file")
    argParser.add_argument("-f","--fps", required=False, help="Overwrite the video capture framerate")
    argParser.add_argument("-v","--verbose",required=False, help="Enable logging in the console")
    argParser.add_argument("-s","--stream",required=False, help="Enable streaming mode - relevant config must be present in json config file.")
    argParser.add_argument("-md","--motiondetection", required=False, help="Force motion detection mode")
    args = vars(argParser.parse_args())
    conf = json.load(open(args["conf"]))
    
    if args["fps"] is not None:
        conf["fps"] = args["fps"]
    if args["verbose"] is not None:
        conf["verbose"] = args["verbose"]
    if args["stream"] is not None:
        conf["stream"] = args["stream"]
    if args["motiondetection"] is not None:
        conf["motiondetection"] = args["motiondetection"]
    return conf


def generate_filepath(config, ft, ts):
    path = config['save_path']
    file_name = f"SPiCam_{ts}.{ft}"
    return f"{path}/{file_name}", file_name
    
def gen_dbx_folder_name():
    dt = datetime.datetime.now()
    return dt.strftime("%Y%m%d")


def start_video_capture(config, file_ts, cam, client):
    sw_print("Starting video capture","INFO",config)
    filepath, fn = generate_filepath(config, "h264", file_ts)
    mp4_fn = fn.replace(".h264", ".mp4")
    cam.start_recording(filepath, format="h264")
    cam.wait_recording(config["recording_length"])
    cam.stop_recording()
    sw_print(f"Recording finished. File saved to {filepath}","INFO", config)
    sw_print(f"Starting MP4 Conversion","INFO", config)
    subprocess.call(f"/home/pi/gpac/bin/gcc/MP4Box -add {filepath} images/{mp4_fn} >/dev/null 2>&1", shell=True)
    sw_print(f"Finished MP4 Conversion, cleaning up raw files","INFO", config)
    os.remove(filepath)
    sw_print("Starting dropbox upload","INFO",config)
    err = 0
    try:
        with open(filepath.replace(".h264",".mp4"),"rb") as f:
            client.files_upload(f.read(), f"/images/{gen_dbx_folder_name()}/{mp4_fn}")
    except Exception as e:
        err = 1
        sw_print(f"Error with dropbox upload: {e}", "ERROR",config)
    if not err:
        sw_print("Dropbox upload complete","INFO",config)

def write_image(frame, config, ts):
    filepath, fn = generate_filepath(config, "jpg", ts)
    cv2.imwrite(filepath, frame)
    sw_print(f"Saved file {filepath} locally", "INFO", config)

def gen_timestamps():
    timestamp = datetime.datetime.now()
    return timestamp.strftime("%A %d %B %Y %I:%M:%S%p"), timestamp.strftime("%Y%m%d_%H_%M_%S"), timestamp

def motion_detection_loop(config, cam, client):
    reso = tuple(config["resolution"])
    raw_capture = PiRGBArray(cam, size=reso)
    sw_print("Camera warming up",  "INFO", config)
    time.sleep(config["warmup_secs"])
    avg = None
    lastUploaded = datetime.datetime.now()
    motion_count = 0
    for f in cam.capture_continuous(raw_capture, format="bgr", use_video_port=True):  
        raw_capture.truncate()
        raw_capture.seek(0)
        frame = f.array
        text = "Unoccupied"

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21,21),0)
        if avg is None:
            sw_print("Starting background model","INFO", config)
            avg = gray.copy().astype("float")
            raw_capture.truncate()
            raw_capture.seek(0)
            continue

        cv2.accumulateWeighted(gray,avg,0.5)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

        thresh = cv2.threshold(frame_delta, config["delta_thresh"],255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = imutils.grab_contours(cnts)

        for c in cnts:
            if cv2.contourArea(c) < config["min_area"]:
                continue
            
            (x, y, w, h) = cv2.boundingRect(c)
            cv2.rectangle(frame, (x,y), (x+w,y+h), (0,255,0),2)
            text = "Occupied"
        
        visual_ts, file_ts, ts = gen_timestamps()

        cv2.putText(frame, f"Room status: {text}", (10,20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0,255),2)
        cv2.putText(frame, visual_ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0,0,255), 1)

        if text == "Occupied":
            if (ts - lastUploaded).seconds >= config["min_motion_frames"]:
                motion_count += 1
                if motion_count >= config["min_motion_frames"]:
                    start_video_capture(config, file_ts, cam, client)
                    lastUploaded = ts
                    motion_count = 0
        else:
            motion_count = 0

    

def main():
    config = sanity_check()
    utils.print_title("SPiCam")
    client = None
    if config["dbx_enabled"]:
        try:
            client = dropbox.Dropbox(config["dbx_access_token"])
            sw_print("Dropbox client connected","INFO",config)
        except Exception as e:
            sw_print(f"Dropbox client failed to connect with error {e}", "ERROR", config)
    if config["stream"] and not config["motiondetection"]:
        stream.start_flask_server()
    else:
        with PiCamera() as cam:
            reso = tuple(config["resolution"])
            cam.resolution = reso
            cam.framerate = config["fps"]
            try:
                motion_detection_loop(config, cam, client)
            except KeyboardInterrupt as e:
                sw_print("Exiting application.", "ERROR", config)
                exit(0)

if __name__ == "__main__":
    main()
