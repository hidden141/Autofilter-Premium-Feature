#!/usr/bin/env python3
"""
ROAROIC Movie Bot promotional poster generator
Requires: Pillow (pip install pillow)

Run:
    python roaroic_poster.py
Optional:
    python roaroic_poster.py --output my_poster.png --font /path/to/font.ttf
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import argparse, math, os, random

W, H = 1024, 1536

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

def find_font(custom=None, bold=False):
    candidates = []
    if custom:
        candidates.append(custom)
    # fonts bundled with the bot (Render/Docker slim images have no system fonts)
    candidates.append(os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"))
    if bold:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
    else:
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None

def font(size, bold=False, custom=None):
    path = find_font(custom, bold)
    try:
        return ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()

def centered(draw, xy, text, fnt, fill, anchor="mm", stroke_width=0, stroke_fill=(0,0,0)):
    draw.text(xy, text, font=fnt, fill=fill, anchor=anchor,
              stroke_width=stroke_width, stroke_fill=stroke_fill)

def rounded(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def glow_layer(base, box, color, blur=24, radius=30):
    layer = Image.new("RGBA", base.size, (0,0,0,0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=(*color, 150))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(layer)

def gradient_bg():
    im = Image.new("RGB", (W,H))
    pix = im.load()
    for y in range(H):
        for x in range(W):
            vignette = max(0, 1 - math.sqrt(((x-W/2)/(W*.78))**2 + ((y-H/2)/(H*.82))**2))
            blue = int(7 + 13*vignette)
            pix[x,y] = (2 + int(2*vignette), 7 + int(blue*.5), 22 + blue)
    return im.convert("RGBA")

def draw_film_reel(draw, cx, cy, r, color=(0,150,255,150)):
    draw.ellipse((cx-r,cy-r,cx+r,cy+r), outline=color, width=max(3,r//12))
    draw.ellipse((cx-r*.25,cy-r*.25,cx+r*.25,cy+r*.25), outline=color, width=max(2,r//16))
    for a in range(0,360,72):
        px = cx + math.cos(math.radians(a))*r*.56
        py = cy + math.sin(math.radians(a))*r*.56
        rr = r*.18
        draw.ellipse((px-rr,py-rr,px+rr,py+rr), outline=color, width=max(2,r//18))

def draw_clapper(draw, x, y, scale=1):
    ww, hh = int(120*scale), int(68*scale)
    draw.rounded_rectangle((x,y+15*scale,x+ww,y+hh+15*scale), radius=int(8*scale),
                           fill=(10,25,47,255), outline=(80,190,255,255), width=max(2,int(3*scale)))
    draw.polygon([(x,y+15*scale),(x+ww,y),(x+ww,y+15*scale)], fill=(15,32,56,255), outline=(100,205,255,255))
    for k in range(4):
        xx=x+10*scale+k*28*scale
        draw.line((xx,y+2*scale,xx+12*scale,y+14*scale), fill=(220,240,255,255), width=max(2,int(5*scale)))
    centered(draw,(x+ww/2,y+52*scale),"▶",font(int(28*scale),True),(255,255,255,255))

def draw_button(draw, x, y, w, h, color, title, subtitle, link, icon="▶"):
    glow_layer(im, (x,y,x+w,y+h), color[:3], blur=22, radius=h//2)
    rounded(draw,(x,y,x+w,y+h),h//2,(*color,255),outline=(120,225,255,230),width=3)
    # Telegram-style round icon
    cx, cy = x+58, y+h//2
    draw.ellipse((cx-35,cy-35,cx+35,cy+35), fill=(0,153,245,255), outline=(125,235,255,255), width=3)
    centered(draw,(cx,cy+1),"➤",font(36,True),(255,255,255,255))
    tx=x+108
    draw.text((tx,y+13),title,font=font(25,True),fill=(255,255,255,255))
    draw.text((tx,y+43),subtitle,font=font(15),fill=(245,250,255,255))
    # Link capsule (right side, vertically centred)
    lf=font(16,True)
    tw=int(draw.textlength(link,font=lf))+28
    cx0=x+w-70-tw
    rounded(draw,(cx0,cy-15,cx0+tw,cy+15),15,(4,22,55,190),outline=(220,245,255,150),width=1)
    centered(draw,(cx0+tw/2,cy),link,lf,(255,255,255,255))
    centered(draw,(x+w-32,cy),"›",font(48,True),(255,255,255,255))

def build(output, custom_font=None):
    global im
    im=gradient_bg()
    # Ambient neon haze
    haze=Image.new("RGBA",(W,H),(0,0,0,0))
    hd=ImageDraw.Draw(haze)
    for cx,cy,r,col in [(120,180,240,(0,85,255,70)),(900,370,260,(120,0,255,55)),
                        (500,850,320,(0,130,255,35)),(780,1250,250,(0,255,210,28))]:
        hd.ellipse((cx-r,cy-r,cx+r,cy+r),fill=col)
    haze=haze.filter(ImageFilter.GaussianBlur(90))
    im.alpha_composite(haze)
    d=ImageDraw.Draw(im)

    # Decorative movie-wall tiles
    random.seed(8)
    for side in ("left","right"):
        for row in range(4):
            for col in range(2):
                x = (12+col*82) if side=="left" else (W-176+col*82)
                y = 15+row*74
                color=random.choice([(18,42,75,230),(28,24,62,230),(17,55,82,230),(50,25,58,230)])
                rounded(d,(x,y,x+70,y+62),5,color,outline=(35,105,165,150),width=2)
                d.rectangle((x+8,y+8,x+62,y+48),fill=(5,12,31,180))
                d.polygon([(x+22,y+14),(x+46,y+20),(x+34,y+42)],fill=random.choice([(0,180,255,220),(240,65,95,220),(255,165,25,220)]))
                d.line((x+10,y+53,x+60,y+53),fill=(100,190,255,150),width=2)

    # Decorative reels and clapper
    draw_film_reel(d, 56, 418, 40)
    draw_film_reel(d, 968, 418, 40)
    draw_clapper(d, 28, 318, .72)
    draw_film_reel(d, 70, 1494, 34)
    draw_film_reel(d, 954, 1494, 34)

    # Header
    centered(d,(W//2,40),"✦  W E L C O M E  T O  ✦",font(20,True,custom_font),(220,240,255,255))
    centered(d,(W//2,130),"♛",font(66,True,custom_font),(60,190,255,255))
    centered(d,(W//2,205),"ROAROIC",font(86,True,custom_font),(255,255,255,255),stroke_width=2,stroke_fill=(0,120,255,255))
    rounded(d,(300,255,724,309),24,(255,199,0,255),outline=(255,245,100,255),width=2)
    centered(d,(512,282),"MOVIE BOT",font(31,True,custom_font),(5,15,35,255))
    rounded(d,(355,321,669,369),24,(0,126,240,255),outline=(90,220,255,255),width=2)
    centered(d,(512,345),"➤  @roaroic_bot",font(24,True,custom_font),(255,255,255,255))
    centered(d,(512,400),"MOVIES  •  SERIES  •  ENTERTAINMENT",font(22,True,custom_font),(230,245,255,255))
    centered(d,(512,436),"Your Favorite Movie, Just a Search Away!",font(25,True,custom_font),(255,220,50,255))

    # Main search callout
    glow_layer(im,(48,466,976,572),(255,185,0),blur=22,radius=30)
    d=ImageDraw.Draw(im)
    rounded(d,(48,466,976,572),30,(7,20,49,255),outline=(255,205,20,255),width=4)
    centered(d,(512,495),"APNI MAN PASAND MOVIE PAAYE!",font(31,True,custom_font),(255,215,35,255))
    centered(d,(512,535),"Naam search karein aur paayein instantly!",font(23,True,custom_font),(255,255,255,255))

    # Feature grid
    features=[
        ("MOVIES & WEB SERIES","Movies aur web series"),
        ("SMART SEARCH","Search in seconds"),
        ("HD / 4K OPTIONS","Quality choices"),
        ("MULTI-LANGUAGE","Hindi & other languages"),
        ("EASY FILE ACCESS","Find files easily"),
        ("FAST & SIMPLE","Easy to use"),
        ("PREMIUM FEATURES","Where available"),
        ("USER-FRIENDLY","Simple commands"),
    ]
    colors=[(0,115,255),(135,35,255),(255,174,0),(0,185,115),(255,45,100),(0,180,220),(135,35,255),(0,110,245)]
    start_y=600
    for i,(title,sub) in enumerate(features):
        row=i//2; col=i%2
        x=42+col*478; y=start_y+row*94
        c=colors[i]
        glow_layer(im,(x,y,x+460,y+78),c,blur=15,radius=24)
        d=ImageDraw.Draw(im)
        rounded(d,(x,y,x+460,y+78),24,(*c,235),outline=(170,230,255,230),width=2)
        d.ellipse((x+10,y+11,x+66,y+67),fill=(3,17,45,255),outline=(255,255,255,200),width=2)
        symbols=["▣",None,"4K","EN·HI","▤","ϟ","♛","●"]
        if symbols[i] is None:  # magnifier drawn manually
            d.ellipse((x+25,y+24,x+45,y+44),outline=(255,255,255,255),width=4)
            d.line((x+43,y+42,x+53,y+53),fill=(255,255,255,255),width=5)
        else:
            sz = 15 if len(symbols[i])>3 else 25
            centered(d,(x+38,y+39),symbols[i],font(sz,True,custom_font),(255,255,255,255))
        d.text((x+79,y+13),title,font=font(19,True,custom_font),fill=(255,255,255,255))
        d.text((x+79,y+43),sub,font=font(15,False,custom_font),fill=(240,248,255,255))

    # Quick steps banner
    glow_layer(im,(50,1000,974,1090),(0,130,255),blur=20,radius=26)
    d=ImageDraw.Draw(im)
    rounded(d,(50,1000,974,1090),26,(4,18,45,255),outline=(0,190,255,255),width=3)
    centered(d,(512,1028),"SEARCH   ›   SELECT   ›   WATCH",font(27,True,custom_font),(255,220,50,255))
    centered(d,(512,1062),"Search • Request • Watch • Enjoy",font(20,True,custom_font),(255,255,255,255))

    # Telegram destinations
    draw_button(d,70,1110,884,78,(0,115,255),"Main Channel","Latest Movies  •  Web Series  •  Updates","https://t.me/roaroic0")
    draw_button(d,70,1200,884,78,(135,35,230),"Update Movies Channel","New Releases  •  Daily Updates  •  HD","https://t.me/roaroic1")
    draw_button(d,70,1290,884,78,(0,170,85),"Movie Bot","Search  •  Request  •  Instant access","@roaroic_bot")
    draw_button(d,70,1380,884,78,(225,45,45),"Movies Group","Share  •  Discuss  •  Movie lovers","https://t.me/roaroicgroup")

    # Footer
    d=ImageDraw.Draw(im)
    rounded(d,(205,1470,819,1520),24,(5,15,40,255),outline=(0,190,255,255),width=3)
    centered(d,(512,1495),"ROAROIC  •  MOVIES  •  SERIES  •  TELEGRAM",font(17,True,custom_font),(255,255,255,255))
    im.convert("RGB").save(output,quality=95)
    print(f"Poster saved to: {os.path.abspath(output)}")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Generate a ROAROIC movie-bot poster with Pillow.")
    parser.add_argument("--output",default="roaroic_poster.png",help="Output PNG filename")
    parser.add_argument("--font",default=None,help="Optional font file path; use a Devanagari-capable font for Hindi text")
    args=parser.parse_args()
    build(args.output,args.font)
