import copy
import os
import re
import subprocess
import sys
import time
from pathlib import Path, PurePath

SUPPORTED_EXTENSIONS = ['.mp4', '.mkv']

USE_JUMPCUTER: bool = False
STANDARDIZE: bool = True

RESULT_SAMPLE_RATE = 44100
# RESULT_SAMPLE_RATE = 32000  # In a case of too big .wav


def createPath(s):
    # assert (not os.path.exists(s)), "The filepath "+s+" already exists. Don't want to overwrite it. Aborting."
    print(f"Attemptnig to create folder: {s}")
    try:
        Path(s).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False
        # assert False, "Creation of the directory %s failed. (The TEMP folder may already exist. Delete or rename it, and try again.)"


class Movie:
    def __init__(self, source_path: PurePath,
                 destination_path: PurePath):
        self.filename: str = source_path.parts[-1]
        self.source_path: PurePath = source_path
        self.destination_path: PurePath = destination_path

    def get_temp_name(self, desc_word: str, ext: str = ".mp4") -> str:
        # TODO: check whether total path is too long.
        name, extension = os.path.splitext(self.source_path.name)
        return "".join((name, desc_word, ext)).replace(" ", "")

    def get_fps(self):
        command = f"ffmpeg -thread_queue_size -i '{self.source_path}' 2>&1"
        temp_name = self.get_temp_name("params").replace("mp4", "txt")
        with open(temp_name, "w", encoding="utf-8") as f:
            subprocess.call(command, shell=True, stdout=f)

        with open(temp_name, 'r+', encoding="utf-8") as f:
            params = f.read().splitlines()

        # Check fps.
        for line in params:
            m = re.search('Stream #.*Video.* ([0-9]*) fps', line)
            if m is not None:
                return float(m.group(1))


def prepare_path_data(input_path: str,
                      output_path: str,
                      keep_structure: bool) -> [Movie]:
    _input_path = Path(input_path)

    movies: list[Movie] = []
    for extension in SUPPORTED_EXTENSIONS:
        for file in _input_path.rglob(f"*{extension}"):
            abs_out_path = Path(output_path).absolute()
            movies.append(
                Movie(
                    file.absolute(),
                    abs_out_path / PurePath(*file.parts[1:-1])) if keep_structure else abs_out_path
                )
    return movies


def get_standardize_command(file: Movie, target_filename, threads: int = 12) -> (str, str, str):
    ffmpeg = "ffmpeg"
    out_args = f" -threads {threads}" \
               f" -ar {RESULT_SAMPLE_RATE}" \
               " -filter:v fps=fps=10" \
               " -max_muxing_queue_size 4096"  # " -vf scale=1600:-2,setsar=1:1"
    command = f"{ffmpeg} -i '{file.source_path}' {out_args} '{target_filename}'"

    return command


def standardize_non_block(file: Movie, target_filename, threads: int = 12):
    command = get_standardize_command(file=file, target_filename=target_filename, threads=threads)

    print(f"Standardizing: {command}...")
    return subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # print(f"Finished, moving to target location: {temp_filename} -> {target_filename}")
    # os.rename(temp_filename, target_filename)


def standardize(file: Movie, temp_filename, target_filename):
    command = get_standardize_command(file=file, target_filename=temp_filename)

    print(f"Standardizing: {command}...")
    subprocess.Popen(command, shell=True).wait()
    # os.system(command)

    print(f"Finished, moving to target location: {temp_filename} -> {target_filename}")
    os.rename(temp_filename, target_filename)


def start(input_path: str, output_path: str, keep_structure: bool = True, concurrent: int = 4):
    files_to_proceed = prepare_path_data(input_path, output_path, keep_structure)

    if STANDARDIZE:
        running_procs: {subprocess.Popen: Movie} = {}
        for file in files_to_proceed:
            target_filename = file.get_temp_name('Standardized')

            if os.path.isfile(target_filename):
                print(f"Using cached version of {target_filename}")
                continue

            while len(running_procs) >= concurrent:
                finished_procs = []
                for proc in running_procs:
                    retcode = proc.poll()
                    if retcode is not None:  # Finished.
                        print(f"Finished {running_procs[proc].filename}")
                        finished_procs.append(proc)
                if finished_procs:
                    for fin in finished_procs:
                        running_procs.pop(fin)
                else:
                    time.sleep(60)

            print(f"Starting {file.filename}")
            proc = standardize_non_block(file=file, target_filename=target_filename, threads=4)
            running_procs[proc] = file

        print("Waiting for all process to finish.")
        for proc in running_procs:
            proc.communicate()
            print(f"Finished {running_procs[proc].filename}")
        running_procs = []

    for file in files_to_proceed:
        print(f"Proceeding with {file.source_path}")

        temp_filename = file.get_temp_name('Standardized')

        # TODO: implement retrieving FPS directly from file. (made in jumpcutter)

        if USE_JUMPCUTER:
            jumpcutter_temp_folder_name, _ = os.path.splitext(temp_filename)

            jumpcutter_temp_output_filename = file.get_temp_name("_SpeedingUp")
            jumpcutter_temp_full_output_path = os.path.join(file.destination_path, jumpcutter_temp_output_filename)

            jumpcutter_params = f" --input_file '{temp_filename}'" \
                                f" --output_file '{jumpcutter_temp_full_output_path}'" \
                                f" --threads  12" \
                                f" --temp_folder_name '{jumpcutter_temp_folder_name}'" \
                                f" --sample_rate '{RESULT_SAMPLE_RATE}'"

            python_interpreter = sys.executable
            jumpcutter_command = f"{python_interpreter} jumpcutter.py {jumpcutter_params}"
            print(f"Calling \n{jumpcutter_command}")
            os.system(jumpcutter_command)
            temp_filename = jumpcutter_temp_full_output_path

        _target_filename, _extension = os.path.splitext(file.filename)
        full_output_path = os.path.join(file.destination_path, _target_filename) + ".mp4"

        createPath(file.destination_path)
        try:
            os.rename(temp_filename, full_output_path)

            if not os.path.isfile(full_output_path):
                time.sleep(2)  # Wait for system to finish rename.
                input(f"FAILED SAVING FILE: {full_output_path}")
        except FileNotFoundError:
            print(f"Cannot os.rename({temp_filename}, {full_output_path})")

        # noinspection PyBroadException
        # try:
        #     os.remove(filename_after_standardization)
        # except Exception:
        #     pass


if __name__ == '__main__':
    start("To proceed", "Proceeded", keep_structure=True)