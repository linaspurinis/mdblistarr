import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BADGE_MARGIN_RATIO = 0.035
BADGE_PADDING_RATIO = 0.55
BADGE_HEIGHT_RATIO = 0.075
BADGE_RADIUS_RATIO = 0.16
BADGE_FG = (255, 255, 255, 255)
AGE_BADGE_BG = (17, 17, 17, 235)

SHADOW_OFFSET_RATIO = 0.012
SHADOW_BLUR_RATIO = 0.01
SHADOW_COLOR = (0, 0, 0, 160)

# Same 6-bucket scale mdblist.com and the iOS app use for the score pill,
# evaluated against the raw 0-100 mdblist score.
SCORE_COLOR_STOPS = (
    (90, (0, 112, 0)),      # #007000
    (80, (35, 136, 35)),    # #238823
    (60, (76, 175, 80)),    # #4CAF50
    (40, (255, 191, 0)),    # #FFBF00
    (1, (210, 34, 45)),     # #D2222D
)
SCORE_COLOR_UNRATED = (113, 122, 127)  # #717A7F, shown as "?"


def _score_color(score):
    for threshold, color in SCORE_COLOR_STOPS:
        if score >= threshold:
            return color
    return SCORE_COLOR_UNRATED


def _format_score(score):
    if score is None or score <= 0:
        return '?'
    text = f"{score / 10:.1f}"
    return text[:-2] if text.endswith('.0') else text


def _font_for_height(pixel_height):
    try:
        return ImageFont.load_default(size=pixel_height)
    except TypeError:
        # Older Pillow without the `size` kwarg on load_default().
        return ImageFont.load_default()


def _badge_geometry(image_size, text, font, anchor):
    width, height = image_size
    margin = int(round(min(width, height) * BADGE_MARGIN_RATIO))
    badge_height = int(round(height * BADGE_HEIGHT_RATIO))

    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    padding_x = int(round(badge_height * BADGE_PADDING_RATIO))
    badge_width = text_width + padding_x * 2
    radius = int(round(badge_height * BADGE_RADIUS_RATIO))

    if anchor == 'top-left':
        x0, y0 = margin, margin
    else:
        x0 = width - margin - badge_width
        y0 = height - margin - badge_height

    return {
        'box': [x0, y0, x0 + badge_width, y0 + badge_height],
        'radius': radius,
        'text_bbox': bbox,
        'text_width': text_width,
        'text_height': text_height,
    }


def _draw_shadow(shadow_draw, geometry):
    offset = geometry['shadow_offset']
    x0, y0, x1, y1 = geometry['box']
    shadow_draw.rounded_rectangle(
        [x0 + offset, y0 + offset, x1 + offset, y1 + offset],
        radius=geometry['radius'], fill=SHADOW_COLOR,
    )


def _draw_badge(draw, geometry, text, font, bg_color):
    x0, y0, x1, y1 = geometry['box']
    bbox = geometry['text_bbox']
    draw.rounded_rectangle([x0, y0, x1, y1], radius=geometry['radius'], fill=(*bg_color, 235))
    text_x = x0 + (geometry['box'][2] - x0 - geometry['text_width']) / 2 - bbox[0]
    text_y = y0 + (geometry['box'][3] - y0 - geometry['text_height']) / 2 - bbox[1]
    draw.text((text_x, text_y), text, font=font, fill=BADGE_FG)


def render_badges(image_bytes, score=None, age_rating=None):
    """
    Composite an mdblist score badge (top-left, color-coded the same way
    mdblist.com and the iOS app color their score pill — green/amber/red by
    the raw 0-100 score, displayed on the familiar 0-10 scale) and an age
    rating badge (bottom-right) onto a poster image. Returns JPEG bytes.
    Pass score=None/age_rating=None to skip either badge.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert('RGBA')
    width, height = image.size
    badge_height = int(round(height * BADGE_HEIGHT_RATIO))
    font = _font_for_height(int(round(badge_height * 0.6)))
    shadow_offset = int(round(min(width, height) * SHADOW_OFFSET_RATIO))
    blur_radius = max(1, int(round(min(width, height) * SHADOW_BLUR_RATIO)))

    badges = []
    if score is not None:
        text = _format_score(score)
        color = _score_color(score) if score > 0 else SCORE_COLOR_UNRATED
        geometry = _badge_geometry(image.size, text, font, 'top-left')
        badges.append((text, color, geometry))
    if age_rating:
        text = f"age {age_rating}"
        geometry = _badge_geometry(image.size, text, font, 'bottom-right')
        badges.append((text, AGE_BADGE_BG[:3], geometry))

    shadow_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    for _, _, geometry in badges:
        geometry['shadow_offset'] = shadow_offset
        _draw_shadow(shadow_draw, geometry)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(blur_radius))

    badge_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge_layer)
    for text, color, geometry in badges:
        _draw_badge(badge_draw, geometry, text, font, color)

    composited = Image.alpha_composite(image, shadow_layer)
    composited = Image.alpha_composite(composited, badge_layer).convert('RGB')
    buffer = io.BytesIO()
    composited.save(buffer, format='JPEG', quality=90)
    return buffer.getvalue()
