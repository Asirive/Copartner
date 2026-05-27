"""Generate Asirive logo icons in all required sizes for Tauri."""
from PIL import Image, ImageDraw
import struct
import os

# Asirive brand colors
BG = (0xEA, 0xFF, 0x00)  # #eaff00
FG = (0x00, 0x00, 0x00)  # #000000

# Scale factor: logo is 100x100, we'll render at target size
# The rectangles are at: x20,y20,w20,h40 | x20,y70,w20,h10 | x60,y40,w20,h40 | x60,y20,w20,h10 | x40,y40,w20,h20
RECTS = [
    (20, 20, 40, 60),   # left tall
    (20, 70, 40, 80),   # left bottom
    (60, 40, 80, 80),   # right tall
    (60, 20, 80, 30),   # right top
    (40, 40, 60, 60),   # center bridge
]

def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (*BG, 255))
    draw = ImageDraw.Draw(img)
    scale = size / 100.0
    for x1, y1, x2, y2 in RECTS:
        sx1, sy1 = int(x1 * scale), int(y1 * scale)
        sx2, sy2 = int(x2 * scale), int(y2 * scale)
        draw.rectangle([sx1, sy1, sx2, sy2], fill=FG)
    return img

def save_png(path: str, size: int):
    render(size).save(path, "PNG")

def save_ico(path: str, sizes=[16, 24, 32, 48, 64, 128, 256]):
    """Save multi-resolution ICO file."""
    images = []
    for s in sizes:
        img = render(s)
        # ICO needs BMP format for alpha on some sizes
        if s <= 64:
            # Use PNG format within ICO for transparency
            images.append(img)
        else:
            images.append(img)
    images[0].save(path, format='ICO', sizes=[(s, s) for s in sizes], append_images=images[1:])

def save_icns(path: str, sizes=[16, 32, 64, 128, 256, 512, 1024]):
    """Save ICNS file (macOS icon format)."""
    # ICNS format is complex; we'll generate PNGs and use a simple approach
    # Actually PIL doesn't support ICNS writing natively
    # We'll create a directory with the PNGs for now and let the user convert
    # Or we can skip ICNS since the user is on Windows
    pass

def main():
    icons_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Standard sizes
    sizes = {
        "32x32.png": 32,
        "128x128.png": 128,
        "128x128@2x.png": 256,
        "icon.png": 512,
        "Square30x30Logo.png": 30,
        "Square44x44Logo.png": 44,
        "Square71x71Logo.png": 71,
        "Square89x89Logo.png": 89,
        "Square107x107Logo.png": 107,
        "Square142x142Logo.png": 142,
        "Square150x150Logo.png": 150,
        "Square284x284Logo.png": 284,
        "Square310x310Logo.png": 310,
        "StoreLogo.png": 50,
    }
    
    for filename, size in sizes.items():
        path = os.path.join(icons_dir, filename)
        save_png(path, size)
        print(f"Generated {filename} ({size}x{size})")
    
    # ICO file
    ico_path = os.path.join(icons_dir, "icon.ico")
    save_ico(ico_path)
    print(f"Generated icon.ico")
    
    # For ICNS on macOS, we'd need an external tool. Skip for now.
    print("Done! Note: icon.icns needs manual conversion on macOS (or use iconutil)")

if __name__ == "__main__":
    main()
