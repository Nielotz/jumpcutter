# TODO:
#   Performance: 
#       Store images in bigger blobs (currently 2h@1600p has 420000 files and 30GB)

from contextlib import closing
from pathlib import Path

from PIL import Image
import subprocess
from audiotsm import phasevocoder
from audiotsm.io.wav import WavReader, WavWriter
from scipy.io import wavfile
import numpy as np
import re
import math
from shutil import copyfile, rmtree
import os
import argparse
from pytube import YouTube
import time
import sys

FUCK_ON_FAIL = False

print(f"Called jumpcutter with params: {' '.join(sys.argv[1:])}")

def downloadFile(url):
    name = YouTube(url).streams.first().download()
    newname = name.replace(' ','_')
    os.rename(name,newname)
    return newname

def getMaxVolume(s):
    maxv = float(np.max(s))
    minv = float(np.min(s))
    return max(maxv,-minv)

def copyFrame(inputFrame, outputFrame):
    src = TEMP_FOLDER + "/frame{:06d}".format(inputFrame + 1) + ".jpg"
    if not os.path.isfile(src):
        return False
        
    dst = TEMP_FOLDER + "/newFrame{:06d}".format(outputFrame + 1) + ".jpg"
    copyfile(src, dst)
    return True

def inputToOutputFilename(filename):
    dotIndex = filename.rfind(".")
    return filename[:dotIndex]+"_ALTERED"+filename[dotIndex:]

def createPath(s):
    #assert (not os.path.exists(s)), "The filepath "+s+" already exists. Don't want to overwrite it. Aborting."
    print(f"Attemptnig to create folder: {s}")
    try:  
        Path(s).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:  
        return False
        #assert False, "Creation of the directory %s failed. (The TEMP folder may already exist. Delete or rename it, and try again.)"

def deletePath(s): # Dangerous! Watch out!
    try:  
        rmtree(s,ignore_errors=False)
    except OSError:  
        print ("Deletion of the directory %s failed" % s)
        print(OSError)

def parse_args():
    parser = argparse.ArgumentParser(description='Modifies a video file to play at different speeds when there is sound vs. silence.')
    parser.add_argument('--input_file', type=str,  help='the video file you want modified')
    parser.add_argument('--url', type=str, help='A youtube url to download and process')
    parser.add_argument('--output_file', type=str, default="", help="the output file. (optional. if not included, it'll just modify the input file name)")
    parser.add_argument('--silent_threshold', type=float, default=0.04, help="the volume amount that frames' audio needs to surpass to be consider \"sounded\". It ranges from 0 (silence) to 1 (max volume)")
    parser.add_argument('--sounded_speed', type=float, default=1, help="the speed that sounded (spoken) frames should be played at. Typically 1.")
    parser.add_argument('--silent_speed', type=float, default=7, help="the speed that silent frames should be played at. 999999 for jumpcutting.")
    parser.add_argument('--frame_margin', type=float, default=1, help="some silent frames adjacent to sounded frames are included to provide context. How many frames on either the side of speech should be included? That's this variable.")
    parser.add_argument('--sample_rate', type=int, default=48000, help="sample rate of the input and output videos")
    parser.add_argument('--frame_rate', type=float, default=30, help="frame rate of the input and output videos. optional... I try to find it out myself, but it doesn't always work.")
    parser.add_argument('--frame_quality', type=int, default=0, help="quality of frames to be extracted from input video. 1 is highest, 31 is lowest, 3 is the default.")
    parser.add_argument('--temp_folder_name', type=str, default=None, help="1 - images exported")
    parser.add_argument('--threads', type=int, default=None, help="")
    return parser.parse_args()


args = parse_args()

frameRate = 8 or args.frame_rate
SAMPLE_RATE = 16000 or args.sample_rate
SILENT_THRESHOLD = args.silent_threshold
FRAME_SPREADAGE = args.frame_margin
NEW_SPEED = [args.silent_speed, args.sounded_speed]
URL = args.url
FRAME_QUALITY = args.frame_quality
temp_folder_name = args.temp_folder_name
if temp_folder_name:
    temp_folder_name = temp_folder_name.replace('"', "").replace("'", "")

THREADS = args.threads or os.cpu_count()

if args.url != None:
    INPUT_FILE = downloadFile(args.url)
else:
    INPUT_FILE = args.input_file

assert INPUT_FILE != None , "why u put no input file, that dum"
    

if len(args.output_file) >= 1:
    OUTPUT_FILE = args.output_file
else:
    OUTPUT_FILE = inputToOutputFilename(INPUT_FILE)

AUDIO_FADE_ENVELOPE_SIZE = 400 # smooth out transitiion's audio by quickly fading in/out (arbitrary magic number whatever)

if temp_folder_name:
    TEMP_FOLDER = temp_folder_name
    if not os.path.exists(TEMP_FOLDER):
        createPath(TEMP_FOLDER)
else:
    TEMP_FOLDER = "TEMP"
    while not createPath(TEMP_FOLDER):
        TEMP_FOLDER += "i"

LOG_FOLDER = "logs.txt"
with open(LOG_FOLDER, "a+", encoding="utf-8") as log_file:
    log_file.write(f"Parsing: {INPUT_FILE}\n")


# Perf result = 214s
# Split movie to frames.
# start_time_seconds = int(time.time())
if len(os.listdir(TEMP_FOLDER)) < 3:  # When folder is not filled with frames.
    command = f"ffmpeg -threads {THREADS} -i {INPUT_FILE} -qscale:v {FRAME_QUALITY} {TEMP_FOLDER}/frame%06d.jpg -hide_banner"
    subprocess.call(command, shell=True)

    # with open("perf_log.txt", "a+") as perf_file:
    #     perf_file.write(f"# Split movie to frames: {int(time.time()) - start_time_seconds}sec\n")
    
    
    # Perf result = 4s
    #1 ?
    # start_time_seconds = int(time.time())
audio_file_path = f"{TEMP_FOLDER}/audio.wav"
if not os.path.isfile(audio_file_path):
    command = f"ffmpeg -threads {THREADS} -i {INPUT_FILE} -ab 160k -ac 2 -ar {SAMPLE_RATE} -vn {audio_file_path}"
    subprocess.call(command, shell=True)
    
    # with open("perf_log.txt", "a+") as perf_file:
    #     perf_file.write(f"#1 ?: {int(time.time()) - start_time_seconds}sec\n")
    
    
    # Perf result = 0s
    #2 ?
    # start_time_seconds = int(time.time())

# input("----------------------_|_|_|_|_|_|_|_|_|_|_-----------------------")

input_file_path = f"{TEMP_FOLDER}/input.mp4"
if not os.path.isfile(input_file_path):
    command = f"ffmpeg -threads {THREADS} -i {input_file_path} 2>&1"
    with open(TEMP_FOLDER + "/params.txt", "w", encoding="utf-8") as f:
        subprocess.call(command, shell=True, stdout=f)
    # with open("perf_log.txt", "a+") as perf_file:
    #     perf_file.write(f"#2 ?: {int(time.time()) - start_time_seconds}sec\n")
    
    
    # Perf result = 3s
    # Audio stuff.
    # start_time_seconds = int(time.time())
sampleRate, audioData = wavfile.read(TEMP_FOLDER + "/audio.wav")
audioSampleCount = audioData.shape[0]
maxAudioVolume = getMaxVolume(audioData)

with open(TEMP_FOLDER + "/params.txt", 'r+', encoding="utf-8") as f: 
    params = f.read().splitlines()

if not frameRate:
    # Guessing framerate?
    for line in params:
        m = re.search('Stream #.*Video.* ([0-9]*) fps', line)
        if m is not None:
            frameRate = float(m.group(1))

samplesPerFrame = sampleRate / frameRate

audioFrameCount = int(math.ceil(audioSampleCount / samplesPerFrame))

hasLoudAudio = np.zeros((audioFrameCount))

for i in range(audioFrameCount):
    start = int(i*samplesPerFrame)
    end = min(int((i + 1) * samplesPerFrame), audioSampleCount)
    audiochunks = audioData[start:end]
    maxchunksVolume = float(getMaxVolume(audiochunks)) / maxAudioVolume
    if maxchunksVolume >= SILENT_THRESHOLD:
        hasLoudAudio[i] = 1

# with open("perf_log.txt", "a+") as perf_file:
#     perf_file.write(f"# Audio stuff: {int(time.time()) - start_time_seconds}sec\n")


# Perf result = 0s
#5 ?
# start_time_seconds = int(time.time())

chunks = [[0, 0, 0], ]
shouldIncludeFrame = np.zeros((audioFrameCount))
for i in range(audioFrameCount):
    start = int(max(0, i - FRAME_SPREADAGE))
    end = int(min(audioFrameCount, i + 1 + FRAME_SPREADAGE))
    shouldIncludeFrame[i] = np.max(hasLoudAudio[start:end])
    if (i >= 1 and shouldIncludeFrame[i] != shouldIncludeFrame[i - 1]): # Did we flip?
        chunks.append([chunks[-1][1],i,shouldIncludeFrame[i - 1]])

chunks.append([chunks[-1][1], audioFrameCount, shouldIncludeFrame[i - 1]])
chunks = chunks[1:]

outputAudioData = np.zeros((0, audioData.shape[1]))
outputPointer = 0

# with open("perf_log.txt", "a+") as perf_file:
#     perf_file.write(f"#5 ?: {int(time.time()) - start_time_seconds}sec\n")


# Perf result = 2445s
#6 ?
# start_time_seconds = int(time.time())
# sub_start_time_seconds = start_time_seconds
# sum_of_time_in_seconds: [(int, str()), ] = ([0, "withs"],
#                                            [0, "np.concatenate"],
#                                            )

lastExistingFrame = None
for chunk in chunks:
    audioChunk = audioData[int(chunk[0] * samplesPerFrame):int(chunk[1] * samplesPerFrame)]
    sFile = TEMP_FOLDER + "/tempStart.wav"
    eFile = TEMP_FOLDER + "/tempEnd.wav"
    
    wavfile.write(sFile, SAMPLE_RATE, audioChunk)

    # withs
    # Wav read 1905s.
    # sub_start_time_seconds = int(time.time())

    with WavReader(sFile) as reader:
        with WavWriter(eFile, reader.channels, reader.samplerate) as writer:
            tsm = phasevocoder(reader.channels, speed=NEW_SPEED[int(chunk[2])])
            tsm.run(reader, writer)
    
    # sum_of_time_in_seconds[0][0] += int(time.time()) - sub_start_time_seconds 

    _, alteredAudioData = wavfile.read(eFile)

    # sub_start_time_seconds = int(time.time())

    leng = alteredAudioData.shape[0]
    endPointer = outputPointer + leng
    outputAudioData = np.concatenate((outputAudioData, alteredAudioData / maxAudioVolume))

    # sum_of_time_in_seconds[1][0] += int(time.time()) - sub_start_time_seconds 
    # sub_start_time_seconds = int(time.time())
    # # #

    #outputAudioData[outputPointer:endPointer] = alteredAudioData/maxAudioVolume

    # smooth out transitiion's audio by quickly fading in/out
    
    if leng < AUDIO_FADE_ENVELOPE_SIZE:
        outputAudioData[outputPointer:endPointer] = 0 # audio is less than 0.01 sec, let's just remove it.
    else:
        premask = np.arange(AUDIO_FADE_ENVELOPE_SIZE) / AUDIO_FADE_ENVELOPE_SIZE
        mask = np.repeat(premask[:, np.newaxis], 2, axis=1) # make the fade-envelope mask stereo
        outputAudioData[outputPointer:outputPointer + AUDIO_FADE_ENVELOPE_SIZE] *= mask
        outputAudioData[endPointer - AUDIO_FADE_ENVELOPE_SIZE:endPointer] *= 1 - mask

    startOutputFrame = int(math.ceil(outputPointer / samplesPerFrame))
    endOutputFrame = int(math.ceil(endPointer / samplesPerFrame))


    outFramesSincePrint = 0
    
    # copyframe 312s
    for outputFrame in range(startOutputFrame, endOutputFrame):
        if outFramesSincePrint == 199:
            print(f"{outputFrame + 1} time-altered frames saved.")
            outFramesSincePrint = -1    
        outFramesSincePrint += 1

        inputFrame = int(chunk[0] + NEW_SPEED[int(chunk[2])] * (outputFrame - startOutputFrame))
        didItWork = copyFrame(inputFrame,outputFrame)
        if didItWork:
            lastExistingFrame = inputFrame
        else:
            copyFrame(lastExistingFrame, outputFrame)

    # # #

    outputPointer = endPointer

# TODO: Step down quality / find another way
# Let user fix audio file.
while True:
# Crashes with to big files (2GB or 4GB)
    try:
        wavfile.write(TEMP_FOLDER + "/audioNew.wav", SAMPLE_RATE, outputAudioData)
        break
    except ValueError as e:
        if FUCK_ON_FAIL:
            raise e
        x = input("Audio file is too big :(, retry on input, entery 42 to skip file")
        try:
            if int(x) == 42:
                raise e
        except exception:
            pass


# with open("perf_log.txt", "a+") as perf_file:
#     perf_file.write(f"#6 ?: {int(time.time()) - start_time_seconds}sec\n")
#     perf_file.write(f"\t#6.1: Chunks size:{len(chunks)}sec\n")
#     for sub_result_idx, sub_result in enumerate(sum_of_time_in_seconds):
#         perf_file.write(f"\t#6.{sub_result_idx} {sub_result[1]} sum: {sub_result[0]}, per loop: {sub_result[0] / len(chunks)} sec\n")

'''
outputFrame = math.ceil(outputPointer/samplesPerFrame)
for endGap in range(outputFrame,audioFrameCount):
    copyFrame(int(audioSampleCount/samplesPerFrame)-1,endGap)
'''

# Perf result = 406s
#7 ?
# start_time_seconds = int(time.time())

out_path = Path(OUTPUT_FILE).parent
if not os.path.exists(out_path):
    createPath(out_path)

command = f"ffmpeg -threads {THREADS} -framerate {str(frameRate)} -i {TEMP_FOLDER}/newFrame%06d.jpg -i {TEMP_FOLDER}/audioNew.wav -strict -2 {OUTPUT_FILE}"
subprocess.call(command, shell=True)


# with open("perf_log.txt", "a+") as perf_file:
#     perf_file.write(f"#7 ?: {int(time.time()) - start_time_seconds}sec\n")


# Perf result = 35s
# Delete temp files.
# start_time_seconds = int(time.time())

with open(LOG_FOLDER, "a+", encoding="utf-8") as log_file:
    log_file.write(f"Finished: {INPUT_FILE}\n cleaning...\n")

deletePath(TEMP_FOLDER)

# with open("perf_log.txt", "a+") as perf_file:
#     perf_file.write(f"# Delete temp files: {int(time.time()) - start_time_seconds}sec\n")
