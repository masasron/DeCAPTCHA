import sys
import base64
import logging
import requests
import argparse
import tempfile
from PIL import Image, ImageFilter

def parse_arguments():
    parser = argparse.ArgumentParser(description="DeCAPTCHA")
    parser.add_argument("image_path", help="path to the image file")
    parser.add_argument("--target", help="classification target", required=True)
    parser.add_argument("--preview", type=bool, default=False, help="show preview of the solution")
    parser.add_argument("--blur_radius", type=int, default=2, help="radius for Gaussian blur")
    parser.add_argument("--server_url", default="http://localhost:8080/completion", help="llava server url")
    parser.add_argument("--log_level", default="INFO", help="logging level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    parser.add_argument("--prompt", default="Respond with 1 if image has a {target}, else 0.", help="classification prompt for llava")
    return parser.parse_args()

def load_and_preprocess_image(image_path, blur_radius):
    try:
        image = Image.open(image_path)
    except FileNotFoundError:
        logging.error("File not found: %s", image_path)
        sys.exit(1)
    except IOError:
        logging.error("Error opening the file: %s", image_path)
        sys.exit(1)

    if image.width != image.height:
        logging.error("Image is not a square")
        sys.exit(1)

    return image.filter(ImageFilter.GaussianBlur(radius=blur_radius))

def split_image(image):
    """
    Split the image into 9 squares
    """
    square_size = image.width // 3
    return [image.crop((j * square_size, i * square_size, (j + 1) * square_size, (i + 1) * square_size))
            for i in range(3) for j in range(3)]

def process_squares(squares, server_url, prompt):
    select = []
    for i, square in enumerate(squares):
        tmp_file = tempfile.NamedTemporaryFile(suffix=".jpg")
        square.save(tmp_file.name)
        with open(tmp_file.name, "rb") as f:
            square_base64 = base64.b64encode(f.read()).decode("utf-8")
        tmp_file.close()        
        response = requests.post(server_url, headers={
            "Content-Type": "application/json",
            "Accept": "application/json"
        }, data="{\"stream\":false,\"n_predict\":400,\"temperature\":0.1,\"stop\":[\"</s>\",\"Llama:\",\"User:\"],\"repeat_last_n\":256,\"repeat_penalty\":1.18,\"top_k\":40,\"top_p\":0.5,\"min_p\":0.05,\"tfs_z\":1,\"typical_p\":1,\"presence_penalty\":0,\"frequency_penalty\":0,\"mirostat\":0,\"mirostat_tau\":5,\"mirostat_eta\":0.1,\"grammar\":\"\",\"n_probs\":0,\"image_data\":[{\"data\":\""+square_base64+"\",\"id\":10}],\"cache_prompt\":true,\"slot_id\":-1,\"prompt\":\"USER:[img-10]\\nUSER:"+prompt+"\\nASSISTANT:\"}")
        
        if response.status_code != 200:
            logging.warning("Failed to get response for square %d", i)
            continue

        try:
            jsonData = response.json()
        except ValueError:
            logging.error("Invalid JSON response for square %d", i)
            continue

        description = jsonData.get("content", "")
        logging.info("Square %d: %s", i, description)

        if "1" in description:
            logging.info("Found match in square %d", i)
            select.append(i)

    return select

def main():
    args = parse_arguments()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="[%(levelname)s] %(message)s")
    
    # replace {target} with the target words
    args.prompt = args.prompt.replace("{target}", args.target)

    image = load_and_preprocess_image(args.image_path, args.blur_radius)
    squares = split_image(image)
    selected_squares = process_squares(squares, args.server_url, args.prompt)

    # if no squares are selected, exit
    if not selected_squares:
        logging.error("Failed to solve the CAPTCHA")
        sys.exit(1)

    if len(selected_squares) < 3:
        logging.warning("Less than 3 squares selected")
    if len(selected_squares) > 4:
        logging.warning("More than 4 squares selected")

    if args.preview:
        image = Image.open(args.image_path)
        width, _ = image.size
        square_size = width // 3
        for i in range(9):
            if i not in selected_squares:
                # add dark overlay
                x = (i % 3) * square_size
                y = (i // 3) * square_size
                for j in range(square_size):
                    for k in range(square_size):
                        r, g, b = image.getpixel((x + j, y + k))
                        image.putpixel((x + j, y + k), (r // 2, g // 2, b // 2))
            else:
                # add red border
                x = (i % 3) * square_size
                y = (i // 3) * square_size
                for j in range(square_size):
                    image.putpixel((x + j, y), (255, 0, 0))
                    image.putpixel((x + j, y + square_size - 1), (255, 0, 0))
                    image.putpixel((x, y + j), (255, 0, 0))
                    image.putpixel((x + square_size - 1, y + j), (255, 0, 0))
        image.show()

    print(",".join(map(str, selected_squares)))

if __name__ == "__main__":
    main()