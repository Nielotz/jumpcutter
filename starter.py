import copy
import os
import time
from pathlib import Path, PurePath

SUPPORTED_EXTENSIONS = ['.mp4', '.mkv']


class Movie:
    def __init__(self, source_path: PurePath,
                 destination_path: PurePath,
                 folder_path_to_create: PurePath):
        self.filename: str = source_path.parts[-1]
        self.source_path: PurePath = source_path
        self.destination_path: PurePath = destination_path
        self.folder_path_to_create: PurePath = folder_path_to_create

    def get_temp_name(self, desc_word: str) -> str:
        # TODO: check whether total path is too long.
        name, extension = os.path.splitext(self.source_path.name)
        return "".join((name, desc_word, extension)).replace(" ", "")


def prepare_path_data(input_path: str,
                      output_path: str) -> [Movie]:
    _input_path = Path(input_path)

    return [Movie(file.absolute(),
                          Path(output_path).absolute(),
                          PurePath(*file.parts[1:-1])
                          )
            for file in _input_path.rglob(f"*{SUPPORTED_EXTENSIONS}")
            ]


def reduce_resolution_and_convert_to_mp4(file: Movie) -> str:
    temp_name = file.get_temp_name('Normalizing')

    ffmpeg = "ffmpeg"
    args = "-threads 12 -vf scale=1600:-2,setsar=1:1"
    command = f"{ffmpeg} -i '{file.source_path}' {args} '{temp_name}'"
    # TODO: implement logging.

    print(f"Executing: {command}...")
    os.system(command)
    print("Finished")
    name = file.get_temp_name('Normalized')
    os.rename(temp_name, name)

    return name


def start(input_path: str, output_path: str):
    files_to_proceed = prepare_path_data(input_path, output_path)
    for file in files_to_proceed:
        print(f"Proceeding with {file.source_path}")
        temp_filename = file.get_temp_name("")

        print(f"Reducing resolution to 1600...")
        temp_filename = reduce_resolution_and_convert_to_mp4(file)
        # temp_filename = 'SieciKomputerowe-wyklady-2Normalized.mp4'
        time.sleep(2)

        # TODO: implement retrieving FPS directly from file.
        # print(f"Analyzing FPS...")

        temp_folder_name = os.path.splitext(temp_filename)[0]

        _filename, _extension = os.path.splitext(file.filename)
        temp_output_filename = file.get_temp_name("_SpeedingUp")

        temp_full_output_path = os.path.join(file.destination_path, temp_output_filename)
        full_output_path = os.path.join(file.destination_path, file.filename)

        jumpcutter_params = f" --input_file {temp_filename}"\
                            f" --output_file {temp_full_output_path}"\
                            f" --threads  12"\
                            f" --temp_folder_name {temp_folder_name}"

        jumpcutter_command = f"python3 jumpcutter.py {jumpcutter_params}"
        print(f"Calling \n{jumpcutter_command}")
        os.system(jumpcutter_command)
        os.rename(temp_full_output_path, full_output_path)
        time.sleep(2)


if __name__ == '__main__':
    start("To proceed", "Proceeded")
