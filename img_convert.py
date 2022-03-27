import os
import argparse
from posixpath import basename
import filedate
import shutil
import tempfile
import subprocess
from pprint import pprint
from PIL import Image
from pathlib import Path

source_dir = Path(__file__).resolve().parent

tmp_root = r"a:"
if os.path.exists(tmp_root):
    tmp_dir = os.path.join(tmp_root, "tmp")
else:
    tmp_dir = None


class BaseConvert:
    exif_path = "exiftool"

    def __init__(self, exif_path = None) -> None:
        super().__init__()
        if exif_path:
            self.exif_path = exif_path

    def copy_exif(self, source_file, dest_file):
        if not (os.path.exists(source_file) and os.path.exists(dest_file)):
            return False

        res = subprocess.getoutput(f'''"{self.exif_path}" -overwrite_original -TagsFromFile "{source_file}" "{dest_file}"''')  
        return "1 image files updated" in res

    def get_exif_date(self, source_file):
        source_file = os.path.normpath(source_file)
        if not (os.path.exists(source_file)):
            return None

        res = subprocess.getoutput(f'''"{self.exif_path}" -T -DateTimeOriginal -d "%Y.%m.%d %H:%M:%S" "{source_file}"''')  
        if res.endswith("-"):
            return None

        return res # datetime.datetime.strptime(res, "%Y.%m.%d %H:%M:%S").timestamp()

    def update_file_date_from_old_file_date(self, source_file, dest_file):
        dt = min(filedate.File(source_file).get().values()) 
        return filedate.File(dest_file).set(created = dt, modified = dt, accessed = dt)

    def update_file_date_from_old_file(self, source_file, dest_file):
        dt = self.get_exif_date(source_file)
        if dt is None:
            return self.update_file_date_from_old_file_date(source_file, dest_file)
        try:
            return filedate.File(dest_file).set(created = dt, modified = dt, accessed = dt)        
        except Exception as e:
            print("WARNING: update_file_date_from_old_file -", e)
            return self.update_file_date_from_old_file_date(source_file, dest_file)

    def norm_ext(self, file_name, extentions):
        lower_extentions = map(str.lower, extentions) 
        basename, extention = os.path.splitext(file_name)
        if extention.lower() not in lower_extentions:
            if extention == ".":
                return basename + extentions[0]
            else:
                return file_name + extentions[0]
        return file_name

class HeicEnc(BaseConvert):
    heicenc_path = "heif-enc"

    def __init__(self, heicenc_path = None, exif_path = None) -> None:
        super().__init__(exif_path)
        if heicenc_path:
            self.heicenc_path = heicenc_path

    def convert_to_heic(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 100 (max)
        out_file_name = self.norm_ext(out_file_name, [".heic"])
        subprocess.check_output(f'"{self.heicenc_path}" -q {quality} -o "{out_file_name}" "{in_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def convert_to_avif(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 100 (max)
        out_file_name = self.norm_ext(out_file_name, [".avif"])
        subprocess.check_output(f'"{self.heicenc_path}" -q {quality} -A -o "{out_file_name}" "{in_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def get_function(self, format):
        if format == "heic":
            return self.convert_to_heic, (0, 100)
        elif format == "avif":
            return self.convert_to_avif, (0, 100)
        return None        


class AvifEnc(BaseConvert):
    avifenc_path = "avifenc"
    speed = 6
    codec = "aom"
    threads = 4

    def __init__(self, avifenc_path=None, speed=None, codec=None, threads=None, exif_path = None) -> None:
        super().__init__(exif_path)
        if avifenc_path is not None:
            self.avifenc_path = avifenc_path
        if speed is not None:
            self.speed = speed
        if codec is not None:
            self.codec = codec
        if threads is not None:
            self.threads = threads

    def convert_to_avif(self, in_file_name, out_file_name, quality):
        # quality - 1 (max) ... 63 (min)
        # codec = aom, rav1e
        out_file_name = self.norm_ext(out_file_name, [".avif"])
        subprocess.check_output(f'"{self.avifenc_path}" --min {quality} --max {quality} -s {self.speed} -c {self.codec} -j {self.threads} "{in_file_name}" "{out_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def get_function(self, format, speed=None, codec=None, threads=None):
        if format == "avif":
            if speed is None:
                speed = self.speed
            if codec is None:
                codec = self.codec
            if threads is None:
                threads = self.threads
            return AvifEnc(self.avifenc_path, speed, codec, threads, self.exif_path).convert_to_avif, (63, 1)
        return None


class Pillow(BaseConvert):
    def __init__(self, exif_path = None) -> None:
        super().__init__(exif_path)

    def convert_to_jpeg(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 95 (max)
        out_file_name = self.norm_ext(out_file_name, [".jpg", ".jpeg"])
        with Image.open(in_file_name) as image:
            image.save(out_file_name, format="jpeg", quality=int(quality), **image.info, optimize=True)
        return out_file_name, os.path.getsize(out_file_name)

    def convert_to_jpeg2000(self, in_file_name, out_file_name, quality):
        # quality - 1 (max) ... n (compsession scale factor)
        out_file_name = self.norm_ext(out_file_name, [".jp2"])
        with Image.open(in_file_name) as image:
            image.save(out_file_name, format="jpeg2000", **image.info, quality_mode="rates", quality_layers=[float(quality)])
        return out_file_name, os.path.getsize(out_file_name)
    
    def convert_to_webp(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 100 (max)    
        out_file_name = self.norm_ext(out_file_name, [".webp"])
        with Image.open(in_file_name) as image:
            image.save(out_file_name, format="webp", quality=int(quality), exif=image.info["exif"])
        return out_file_name, os.path.getsize(out_file_name)

    def get_function(self, format):
        if format == "jpeg":
            return self.convert_to_jpeg, (0, 100)
        elif format == "jpeg2000":
            return self.convert_to_jpeg2000, (100, 0)
        elif format == "webp":
            return self.convert_to_webp, (0, 100)
        return None

class Magick(BaseConvert):
    magick_path = "magick"

    def __init__(self, magick_path = None, exif_path = None) -> None:
        super().__init__(exif_path)
        if magick_path:
            self.magick_path = magick_path
        
    def convert_to_jpeg(self, in_file_name, out_file_name, quality):
        # quality - 1 (min) ... 100 (max)
        out_file_name = self.norm_ext(out_file_name, [".jpg", ".jpeg"])
        subprocess.check_output(f'"{self.magick_path}" convert "{in_file_name}" -quality {quality} "{out_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def convert_to_jpeg2000(self, in_file_name, out_file_name, quality):
        # quality - 1 (max) ... n (compsession scale factor)
        out_file_name = self.norm_ext(out_file_name, [".jp2"])
        subprocess.check_output(f'"{self.magick_path}" convert "{in_file_name}" -quality {quality} "{out_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)
    
    def convert_to_avif(self, in_file_name, out_file_name, quality):
        out_file_name = self.norm_ext(out_file_name, [".avif"])
        subprocess.check_output(f'"{self.magick_path}" convert "{in_file_name}" -quality {quality} "{out_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def convert_to_webp(self, in_file_name, out_file_name, quality):
        # quality - 0 (min) ... 100 (max)
        out_file_name = self.norm_ext(out_file_name, [".webp"])
        subprocess.check_output(f'"{self.magick_path}" convert "{in_file_name}" -quality {quality} "{out_file_name}"')
        return out_file_name, os.path.getsize(out_file_name)

    def get_function(self, format):
        if format == "jpeg":
            return self.convert_to_jpeg, (1, 100)
        elif format == "jpeg2000":
            return self.convert_to_jpeg2000, (1, 100)
        elif format == "webp":
            return self.convert_to_webp, (1, 100)
        elif format == "avif":
            return self.convert_to_avif, (1, 100)
        return None

    def auto_orient(self, in_file_name, out_file_name):
        subprocess.check_output(f'"{self.magick_path}" "{in_file_name}" -auto-orient "{out_file_name}"')
        return os.path.exists(out_file_name)
                    
    def psnr(self, original_file_name, test_file_name):
        with tempfile.TemporaryDirectory(prefix=tmp_dir) as tmpdirname:
            res = subprocess.getoutput(f'''"{self.magick_path}" compare -metric PSNR "{original_file_name}" "{test_file_name}" "{os.path.join(tmpdirname, 'tmp.png')}''')
            try:
                res = float(res)
                return res
            except Exception as e:
                print(e, res)
                shutil.copy(test_file_name, os.getcwd()) 
                return None

def optimizer(method_format_name, convert, if_file_name, min_q, max_q, target_ratio):
    print("Optimize:", method_format_name, if_file_name, min_q, max_q, target_ratio)
    result = None
    if os.path.exists("cache.dat"):
        with open("cache.dat") as f:
            cache = eval(f.readline())
    else:
        cache = dict()
        
    with tempfile.TemporaryDirectory(prefix=tmp_dir) as tmpdirname:
        input_file_size = os.path.getsize(if_file_name)
        tmp_file = os.path.join(tmpdirname, "tmp")
        med_q = (max_q + min_q) // 2
        
        med_q_old = -1

        opt_q = -1 
        min_distance = 1000

        while True:
            key = (method_format_name, if_file_name, med_q)
            cached = False
            if key in cache:
                cached = True
                value = cache[key]
            else:
                try:
                    value = convert(if_file_name, tmp_file, med_q)[1]
                except Exception as e:
                    print(e, if_file_name, tmp_file, med_q)
                    raise

                cache[key] = value

            med_q_result = input_file_size / value
            print(f"f({med_q:2.2f}) = {med_q_result:2.2f}{', cached' if cached else ''}")

            distance = abs(med_q_result-target_ratio)
            if distance < min_distance:
                min_distance = distance
                opt_q = med_q

            if med_q_result > target_ratio:
                min_q = med_q
                max_q = max_q
            else:
                min_q = min_q
                max_q = med_q

            med_q_old = med_q
            med_q = (max_q + min_q) // 2

            if med_q_old == med_q:
                break
    
    with open("cache.dat", "w") as f:
        f.write(str(cache))

    print("Optimization result is:", opt_q, "distance:", min_distance)
    return opt_q


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=["pil", "magick", "heicenc", "avifenc", "psnr"], help="pil, magick, heicenc, avifenc")
    parser.add_argument("-f", "--format", default=None, help="""For 'pil' method - jpeg, jpeg2000, webp;
For 'magick' method - jpeg, jpeg2000, webp, avif;
For 'heicenc' method - avif, heic;
For 'avifenc' method - avif.""")
    parser.add_argument("-i", "--input_file", default=None, help="Input file name with path")
    parser.add_argument("-o", "--output_file", default="result", help="Output file name with path with or without extention")
    parser.add_argument("-q", "--quality_level", default=32, help="Quality of encoding")
    parser.add_argument("-c", "--codec", choices=["aom", "rav1e"], default="aom", help="Optional codec selection for 'avifenc' method - aom, rav1e")
    parser.add_argument("-s", "--speed", choices=list(map(str, range(0, 11))), default="6", help="Optional speed selection for 'avifenc' method - integer value in [0..10], 0 is slowest and 10 is fastest")
    parser.add_argument("-t", "--threads", choices=list(map(str, range(0, 33))), default="8", help="Number of parallel CPU threads for 'avifenc' method - integer value in [0..32]")
    parser.add_argument("--optimize", default=None, help="Find a quality value for 2, 3, 4 ratios")
    return parser.parse_args()


if __name__ == "__main__":
    magick_path = Path(r"C:\Program Files\ImageMagick-7.1.0-Q16-HDRI\magick.exe")
    avifenc_path = source_dir / "bin" / "avifenc" / "avifenc-dev.exe"
    heicenc_path = source_dir / "bin" / "heifenc" / "heif-enc.exe"
    exiftool_path = source_dir / "bin" / "extiftool" / "exiftool.exe"

    args = parse_arguments()

    output_file_size = None
    output_file_name = None

    # format_name = args.format
    if args.method == "pil":
        converter = Pillow(exiftool_path)
    elif args.method in ("magick", "psnr"):
        converter = Magick(magick_path, exiftool_path)
    elif args.method == "heicenc":
        converter = HeicEnc(heicenc_path, exiftool_path)
    elif args.method == "avifenc":
        converter = AvifEnc(avifenc_path, args.speed, args.codec, args.threads, exiftool_path)
        # format_name = f"{args.format}_{args.codec}_{args.speed}"

    if converter is None:
        print(f"Unknown method - {args.method}")
        exit(1)

    if args.method == "psnr":
        psnr = converter.psnr(args.input_file, args.output_file)
        print(f"psnr: {psnr}")
    elif args.optimize is not None:
        test_files_count = 9

        converter_function, q_range = converter.get_function(args.format)
        if converter_function is None:
            print(f"Unknown format - {args.format}")
            exit(1)            

        ratios = [2, 3, 4] 
        method_format_name = f"{args.method}_{args.format}"
        if args.method == "avifenc":
            method_format_name = f"{method_format_name}_{args.codec}_{args.speed}_{args.threads}"

        results = {}
        for i in range(1, test_files_count+1):
            for j in ratios:
                if j not in results:
                    results[j] = 0
                results[j] += optimizer(method_format_name, converter_function, f"images\\{i}.jpg", q_range[0], q_range[1], j)

        psnr = Magick(magick_path).psnr

        for j in ratios:
            results[j] = round(results[j] / test_files_count)
            
        psnr_value = {}
        with tempfile.TemporaryDirectory(prefix=tmp_dir) as tmpdirname:            
            tmp_result_path = os.path.join(tmpdirname, "tmp")
            for i in range(1, test_files_count+1):
                input_file = f"images\\{i}.jpg"
                for j, q in results.items(): 
                    if j not in psnr_value:
                        psnr_value[j] = [0, 0]
                    tmp_output_file, _ = converter_function(input_file, tmp_result_path, q)
                    _psnr = psnr(input_file, tmp_output_file)
                    print(input_file, tmp_output_file, _psnr)
                    if _psnr is not None:
                        psnr_value[j][0] += _psnr
                        psnr_value[j][1] += 1

        
        for j, q in results.items(): 
            print(f"Mean q for ratio {j} is {q}, psnr is {psnr_value[j][0] / psnr_value[j][1]:2.2f}")
    else:
        input_file_size = os.path.getsize(args.input_file)
        converter_function, q_range = converter.get_function(args.format)
        if converter_function is None:
            print(f"Unknown format - {args.format}")
            exit(1)            

        output_file_name, output_file_size = converter_function(args.input_file, args.output_file, args.quality_level)
        converter.copy_exif(args.input_file, output_file_name)
        converter.update_file_date_from_old_file(args.input_file, output_file_name)

        if output_file_size: 
            print(f"Input file size: {input_file_size}, Output file size: {output_file_size}, Ratio: {input_file_size/output_file_size:2.2f}")
    