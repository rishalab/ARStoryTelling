# AI Character Image Generator

This Python script generates a realistic AI character image using the Pollinations AI image API.

## Features

* Generates high-quality character images
* Uses custom prompts for character design
* Saves generated image automatically
* Displays the generated image after creation

## Requirements

Install the required libraries:

```bash
pip install requests pillow
```

## Code Overview

The script:

1. Encodes the text prompt
2. Sends a request to the Pollinations AI API
3. Receives the generated image
4. Displays and saves the image as `output.png`

## Run the Script

```bash
python filename.py
```

Replace `filename.py` with your actual Python file name.

## Example Prompt

```python
Full body T-pose, front-facing, dark noble complexion,
tall strong noble king, royal Asura crown - golden,
royal robes, warrior attire, gold necklace, armlets,
earrings, waistband, realistic Hindu Treta Yuga style
```

## Output

Generated image will be saved as:

```bash
output.png
```

## Notes

* Internet connection is required
* Image generation may take a few seconds
* You can modify the prompt to create different characters

## API Used

Pollinations AI Image API:

```bash
https://image.pollinations.ai
```
