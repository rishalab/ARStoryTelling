import requests
import urllib.parse
from PIL import Image
from io import BytesIO
def generate_character_image(prompt):
    encoded_prompt = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?model=flux"
        f"&width=1024"
        f"&height=1792"
        f"&seed=2"
        f"&nologo=true"
    )
    print("Generating image...")
    response = requests.get(url, timeout=120)
    if response.status_code == 200:
        image = Image.open(BytesIO(response.content))
        image.show()
        image.save("output.png")
        print("Image saved as output1.png")
        return image
    else:
        print("Generation failed")
        return none
def main():
    prompt = """
    Full body T-pose, front-facing, dark noble complexion, tall strong noble king, royal Asura crown - golden, royal robes, warrior attire, gold necklace, armlets, earrings, waistband, silently hearing, realistic Hindu Treta Yuga style, neutral background, symmetrical anatomy, no perspective distortion, game-ready topology """
    generate_character_image(prompt)
if __name__ == "__main__":
    main()