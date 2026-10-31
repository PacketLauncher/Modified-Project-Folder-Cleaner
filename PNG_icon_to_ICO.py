from PIL import Image

image = Image.open("Icon.png").convert("RGBA")
image.save("Icon.ico", format="ICO", sizes=[
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256)
])