import os
import sys
import subprocess
import time
import tempfile
import hashlib

from pathlib import Path
from img_convert import AvifEnc, Magick
from video_convert import FFMpegEnc
from multiprocessing import Pool

tmp_root = r"a:"
if os.path.exists(tmp_root):
    tmp_dir = os.path.join(tmp_root, "tmp")
else:
    tmp_dir = None

source_dir = Path(__file__).resolve().parent
avifenc_path = source_dir / "bin" / "avifenc" / "avifenc-dev.exe"
ffmpeg_path = source_dir / "bin" / "ffmpeg_latest" / "ffmpeg.exe"
exiftool_path = source_dir / "bin" / "extiftool" / "exiftool.exe"
magick_path = Path(r"C:\Program Files\ImageMagick-7.1.0-Q16-HDRI\magick.exe")
converter_video = FFMpegEnc(ffmpeg_path, 4, exiftool_path)
converter_image = AvifEnc(avifenc_path, 8, "aom", 4, exiftool_path)
magick = Magick(magick_path, exiftool_path)
q_image = 21 # 8 x 2; 15 x 3; 21 x 4;
q_video = 29.5 # 29.5 x 2;


def read_arguments(_arguments):
    """
    1. Source path
    2. Destination path

    :param _arguments: sys.argv
    :return: list(source, destination)
    """
    if len(_arguments) < 4:
        return None
    else:
        return _arguments[1:]

def get_hash(file_path):
    block_size = 65536
    hash_function = hashlib.sha256()
    with open(file_path, 'rb') as a_file:
        buf = a_file.read(block_size)
        while len(buf) > 0:
            hash_function.update(buf)
            buf = a_file.read(block_size)
    return hash_function.hexdigest()


def write_hash_file(hash_file_path, hash_source_file, hash_archive_file, mtime_source_file, ctime_source_file):
    with open(hash_file_path, "w") as hash_file:
        hash_file.write(hash_source_file + hash_archive_file + "\n")
        hash_file.write(mtime_source_file + "\n")
        hash_file.write(ctime_source_file + "\n")


def read_hash_file(hash_file_path):
    if not os.path.exists(hash_file_path):
        return "", "", None, None

    with open(hash_file_path, "r") as hash_file:
        lines = hash_file.readlines()
    hash_line = lines[0].strip()
    div_position = len(hash_line) // 2
    hash_source_file = hash_line[:div_position]
    hash_archive_file = hash_line[div_position:]
    if len(lines) >= 3:
        mtime_source_file = lines[1].strip()
        ctime_source_file = lines[2].strip()
    else:
        mtime_source_file = None
        ctime_source_file = None
    return hash_source_file, hash_archive_file, mtime_source_file, ctime_source_file


def compress_file(root, source, destination, password):
    start_time = time.time()
    volume_size_mb = 1000
    cmd_m1 = [r"C:\Program Files\7-zip\7z.exe", "a", "-t7z", "-mx1", "-mmt=4", "-bso0", "-v%im" % volume_size_mb]
    cmd_m9 = [r"C:\Program Files\7-zip\7z.exe", "a", "-t7z", "-mx6", "-mmt=4", "-bso0", "-v%im" % volume_size_mb]

    encoded_path = None
    source_path = os.path.join(root, source)
    source_file_name_ext = os.path.split(source)[1]
    source_file_name, source_file_ext = os.path.splitext(source_file_name_ext)
    
    archive_path = os.path.join(destination, source) + ".7z"
    archive_volume_path1 = archive_path + ".001"
    archive_volume_path2 = archive_path + ".002"
    hash_path = os.path.join(destination, source) + ".hash"

    exists_hash_source_file, exists_hash_archive_file, exists_mtime_source_file, exists_ctime_source_file = (None, None, None, None)
    if os.path.exists(hash_path):
        exists_hash_source_file, exists_hash_archive_file, exists_mtime_source_file, exists_ctime_source_file = read_hash_file(hash_path)

    hash_source_file = None
    mtime_source_file = str(os.path.getmtime(source_path))
    ctime_source_file = str(os.path.getctime(source_path))

    file_exists = os.path.exists(archive_path) or os.path.exists(archive_volume_path1)
    dates_are_identical = (exists_mtime_source_file == mtime_source_file) and (exists_ctime_source_file == ctime_source_file)

    if file_exists and not dates_are_identical:
        hash_source_file = get_hash(source_path)
        file_exists = hash_source_file == exists_hash_source_file

    if file_exists:
        if not (exists_mtime_source_file and exists_ctime_source_file):
            write_hash_file(hash_path, exists_hash_source_file, exists_hash_archive_file, mtime_source_file, ctime_source_file)
        print("Skipped: %s" % (source_path, ))
        return 0, 0, 0.0

    with tempfile.TemporaryDirectory(prefix=tmp_dir) as tmpdirname:
        if source_file_ext.lower() in [".jpg", ".jpeg", ".mp4", ".mkv"]:
            result_path = os.path.join(tmpdirname, source_file_name)

            ok = False
            if source_file_ext.lower() in [".jpg", ".jpeg"]:
                converter = converter_image
                try:                
                    result_path_oriented = os.path.join(tmpdirname, source_file_name_ext)
                    magick.auto_orient(source_path, result_path_oriented)
                    encoded_path, encoded_size = converter_image.convert_to_avif(result_path_oriented, result_path, q_image)
                except Exception as e:
                    print("ERROR (Image conversion):", e, encoded_path)
            else:
                converter = converter_video
                try:
                    encoded_path, encoded_size = converter_video.convert_to_hevc_nvenc(source_path, result_path, q_video)
                except Exception as e:
                    print("ERROR (Video conversion):", e, encoded_path)

            if encoded_path is not None: 
                converter.copy_exif(source_path, encoded_path)
                converter.update_file_date_from_old_file(source_path, encoded_path)                

        if encoded_path is not None:
            file_to_archive_path = encoded_path
        else:    
            file_to_archive_path = source_path
            
        source_file_size = os.path.getsize(source_path)
        print("Processing: %s %.2f Mb" % (source_path, source_file_size / (1024*1024)))

        if password:
            cmd_m1.append("-p%s" % password)
            cmd_m9.append("-p%s" % password)

        cmd_m1.extend([archive_path, file_to_archive_path])
        cmd_m9.extend([archive_path, file_to_archive_path])

        if os.path.exists(archive_path):
            os.remove(archive_path)

        for i in range((source_file_size // (1000*1000*(volume_size_mb // 10))) + 1):
            archive_volume_path = archive_path + ".%03i" % i
            if os.path.exists(archive_volume_path):
                os.remove(archive_volume_path)
                
        if source_file_ext.lower() in [".jpg", ".jpeg", ".mp4", ".mkv", ".webp", ".png", ".avi", ".rar", ".7z", ".zip", ".gz"]:
            subprocess.run(cmd_m1)
        else:
            subprocess.run(cmd_m9)

        archive_file_size = os.path.getsize(archive_volume_path1)

        if os.path.exists(archive_volume_path2):
            i = 2
            while True:
                tmp_name = f"{archive_path}.{i:03d}"
                if os.path.exists(tmp_name):
                    archive_file_size += os.path.getsize(tmp_name)
                    i += 1
                else:
                    break
            archive_path = archive_volume_path1                
        else:
            os.rename(archive_volume_path1, archive_path)

        hash_archive_file = get_hash(archive_path)

        if not hash_source_file:
            hash_source_file = get_hash(source_path)
        write_hash_file(hash_path, hash_source_file, hash_archive_file, mtime_source_file, ctime_source_file)

        archive_file_size += os.path.getsize(hash_path)

        end_time = time.time() - start_time
        print("Finished: %s %.2f Mb, %.2f s" % (source_path, archive_file_size / (1024*1024), end_time))
    return source_file_size, archive_file_size, end_time

def compress_files(source, destination, password):
    total_start_time = time.time()
    pure_compressing_time = 0.0
    source_files_size = 0
    archived_files_size = 0
    total_files_count = 0
    processed_files_count = 0
    div_position = len(source) + 1
    workers = []
    pool_size = 2
    with Pool(processes=pool_size) as pool:    
        for root, dirs, files in os.walk(source):
            for i_file in files:
                while len(workers) > pool_size*2:
                    for work in reversed(workers):
                        if work.ready():
                            source_file_size, archived_file_size, compressing_time = work.get()

                            if compressing_time:
                                processed_files_count += 1
                                pure_compressing_time += compressing_time
                                source_files_size += source_file_size
                                archived_files_size += archived_file_size
                            total_files_count += 1
                            workers.remove(work)

                relative_source = os.path.join(root, i_file)[div_position:]
                workers.append(pool.apply_async(compress_file, (source, relative_source, destination, password)))

        total_working_time = time.time() - total_start_time

        while len(workers) > 0:
            for work in reversed(workers):
                if work.ready():
                    source_file_size, archived_file_size, compressing_time = work.get()

                    if compressing_time:
                        processed_files_count += 1
                        pure_compressing_time += compressing_time
                        source_files_size += source_file_size
                        archived_files_size += archived_file_size
                    total_files_count += 1
                    workers.remove(work)
                
    print("Finished")
    print("Statistics:")
    print("\tTotal files count:", total_files_count)
    print("\tTotal files compressed:", processed_files_count)
    print("\tSource files size:  %.2fMb" % (source_files_size / (1024*1024)))
    print("\tArchived files size:  %.2fMb" % (archived_files_size / (1024*1024)))
    print("\tReal working time: %.2fs" % total_working_time)
    print("\tTotal working time: %.2fs" % pure_compressing_time)


def copy_files(source, destination):
    total_start_time = time.time()
    total_files_count = 0
    processed_files_count = 0
    div_position = len(source) + 1
    for root, dirs, files in os.walk(source):
        for i_file in files:
            relative_source = os.path.join(root, i_file)[div_position:]
            # file_size = compress_file(source, relative_source, destination)

            total_files_count += 1
    total_working_time = time.time() - total_start_time

    print("Finished")
    print("Statistics:")
    print("\tTotal files count:", total_files_count)
    print("\tTotal files compressed:", processed_files_count)
    print("\tTotal working time: %.2fs" % total_working_time)


def print_help():
    print(sys.argv)
    print("""Arguments: mode source_path destination_path
          \tModes: compress
          \t\tOptions: password(optional)              
          """)

#          \t       copy
#          \t\tOptions: none


if __name__ == "__main__":
    print("Per file backup v 0.2")
    arguments = read_arguments(sys.argv)
    if not arguments:
        print_help()
        exit(1)
    arguments_count = len(arguments)

    if arguments_count > 1:
        mode = arguments[0]
        if mode not in ("compress", "copy"):
            print_help()
            exit(1)

    print(f"mode: {mode}")
    source_path = arguments[1]
    destination_path = arguments[2]
    if len(arguments) > 4 and mode == "compress":
        archive_password = arguments[3]
    else:
        archive_password = None
    source_path = os.path.abspath(source_path)
    destination_path = os.path.abspath(destination_path)
    if mode == "compress":
        compress_files(source_path, destination_path, archive_password)
    elif mode == "copy":
        copy_files(source_path, destination_path)

