import os
import tempfile
import argparse
import subprocess

from pathlib import Path
from img_convert import BaseConvert

source_dir = Path(__file__).resolve().parent

tmp_root = r"a:"
if os.path.exists(tmp_root):
    tmp_dir = os.path.join(tmp_root, "tmp")
else:
    tmp_dir = None

class FFMpegEnc(BaseConvert):
    ffmpeg_path = "ffmpeg"
    threads = 4

    def __init__(self, ffmpeg_path = None, threads=None, exif_path = None) -> None:
        super().__init__(exif_path)
        if ffmpeg_path:
            self.ffmpeg_path = ffmpeg_path
        if threads is not None:
            self.threads = threads            

    def convert_to_hevc_nvenc(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 100 (max) 
        # bin\ffmpeg_latest\ffmpeg -hide_banner -y -i videos\%file_name% -c:v hevc_nvenc -preset %preset%  -tune hq -profile:v main -b_ref_mode middle -nonref_p 1 -tier high -rc-lookahead 32 -rc vbr -bf 2 -cq %cq% -threads %NUMBER_OF_PROCESSORS% -c:a aac -q:a 2 output\res_latest_%preset%_%cq%_%file_name%
        out_file_name = self.norm_ext(out_file_name, [".mkv"])
        # -c:a aac -q:a 2
        subprocess.check_output(f"{self.ffmpeg_path} -hide_banner -loglevel warning -stats -y -i {in_file_name} -c:v hevc_nvenc -preset p7  -tune hq -profile:v main -b_ref_mode middle -nonref_p 1 -tier high -rc-lookahead 32 -rc vbr -bf 2 -cq {quality} -threads {self.threads} -c:a copy {out_file_name}")
        return out_file_name, os.path.getsize(out_file_name)

    def get_function(self, format):
        if format == "hevc_nvenc":
            return self.convert_to_hevc_nvenc, (51, 1)
        return None        

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=["ffmpeg"], help="ffmpeg")
    parser.add_argument("-f", "--format", default=None, help="""For 'ffmpeg' method - hevc_nvenc;""")
    parser.add_argument("-i", "--input_file", default=None, help="Input file name with path")
    parser.add_argument("-o", "--output_file", default="result", help="Output file name with path with or without extention")
    parser.add_argument("-q", "--quality_level", default=28, help="Quality of encoding")
    # parser.add_argument("-c", "--codec", choices=["aom", "rav1e"], default="aom", help="Optional codec selection for 'avifenc' method - aom, rav1e")
    # parser.add_argument("-s", "--speed", choices=list(map(str, range(0, 11))), default="6", help="Optional speed selection for 'avifenc' method - integer value in [0..10], 0 is slowest and 10 is fastest")
    # parser.add_argument("-t", "--threads", choices=list(map(str, range(0, 33))), default="8", help="Number of parallel CPU threads for 'avifenc' method - integer value in [0..32]")
    # parser.add_argument("--optimize", default=None, help="Find a quality value for 2, 3, 4 ratios")
    return parser.parse_args()

if __name__ == "__main__":
    ffmpeg_path = source_dir / "bin" / "ffmpeg_latest" / "ffmpeg.exe"
    exiftool_path = source_dir / "bin" / "extiftool" / "exiftool.exe"

    args = parse_arguments()

    output_file_size = None
    output_file_name = None

    # format_name = args.format
    if args.method == "ffmpeg":
        converter = FFMpegEnc(ffmpeg_path, exiftool_path)

    if converter is None:
        print(f"Unknown method - {args.method}")
        exit(1)

    input_file_size = os.path.getsize(args.input_file)
    converter_function, q_range = converter.get_function(args.format)
    if converter_function is None:
        print(f"Unknown format - {args.format}")
        exit(1)            

    output_file_name, output_file_size = converter_function(args.input_file, args.output_file, args.quality_level)
    if not converter.copy_exif(args.input_file, output_file_name):
        print("Can not copy Exif")
    converter.update_file_date_from_old_file(args.input_file, output_file_name)

    if output_file_size: 
        print(f"Input file size: {input_file_size}, Output file size: {output_file_size}, Ratio: {input_file_size/output_file_size:2.2f}")
    