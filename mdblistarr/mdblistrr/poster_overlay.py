import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Geometry matched to the iOS app's MDBScoreBadge (Components/MDBScoreBadge.swift):
# minWidth 30 / minHeight 22 / cornerRadius 6 / font size 12 bold, designed
# against a ~115pt poster (the standard 3-column grid card width) — expressed
# here as ratios of the poster's pixel width so it scales to any resolution.
BADGE_MARGIN_RATIO = 0.035
BADGE_HEIGHT_RATIO = 22 / 115
BADGE_MIN_WIDTH_RATIO = 30 / 115
BADGE_RADIUS_RATIO = 6 / 22    # of badge height
BADGE_FONT_RATIO = 12 / 22     # of badge height
BADGE_TEXT_PADDING_RATIO = 0.18  # of badge height; only matters once text exceeds the min-width floor
BADGE_FG = (255, 255, 255, 255)
BADGE_FILL_ALPHA = 242  # ~0.95 opacity, matching MDBScoreBadge's .opacity(0.95)
AGE_BADGE_BG = (17, 17, 17)

# MDBScoreBadge's shadow: .shadow(color: .black.opacity(0.4), radius: 2, x: 0, y: 1) at 115pt design width.
SHADOW_Y_OFFSET_RATIO = 1 / 115
SHADOW_BLUR_RATIO = 2 / 115
SHADOW_COLOR = (0, 0, 0, 102)  # ~0.4 opacity

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


def _badge_geometry(image_size, text, font, anchor, badge_height, min_width, radius, text_padding):
    width, height = image_size
    margin = int(round(min(width, height) * BADGE_MARGIN_RATIO))

    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    content_width = text_width + text_padding * 2
    badge_width = max(min_width, content_width)

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


def _draw_shadow(shadow_draw, geometry, y_offset):
    x0, y0, x1, y1 = geometry['box']
    shadow_draw.rounded_rectangle(
        [x0, y0 + y_offset, x1, y1 + y_offset],
        radius=geometry['radius'], fill=SHADOW_COLOR,
    )


def _draw_badge(draw, geometry, text, font, bg_color):
    x0, y0, x1, y1 = geometry['box']
    bbox = geometry['text_bbox']
    draw.rounded_rectangle([x0, y0, x1, y1], radius=geometry['radius'], fill=(*bg_color, BADGE_FILL_ALPHA))
    text_x = x0 + (x1 - x0 - geometry['text_width']) / 2 - bbox[0]
    text_y = y0 + (y1 - y0 - geometry['text_height']) / 2 - bbox[1]
    draw.text((text_x, text_y), text, font=font, fill=BADGE_FG)


def render_badges(image_bytes, score=None, age_rating=None):
    """
    Composite an mdblist score badge (top-left, color-coded and sized to
    match the iOS app's MDBScoreBadge component) and an age rating badge
    (bottom-right, same proportions for visual consistency) onto a poster
    image. Returns JPEG bytes. Pass score=None/age_rating=None to skip
    either badge.
    """
    image = Image.open(io.BytesIO(image_bytes)).convert('RGBA')
    width, height = image.size
    badge_height = int(round(width * BADGE_HEIGHT_RATIO))
    min_width = int(round(width * BADGE_MIN_WIDTH_RATIO))
    radius = int(round(badge_height * BADGE_RADIUS_RATIO))
    text_padding = badge_height * BADGE_TEXT_PADDING_RATIO
    font = _font_for_height(int(round(badge_height * BADGE_FONT_RATIO)))
    shadow_y_offset = max(1, int(round(width * SHADOW_Y_OFFSET_RATIO)))
    blur_radius = max(1, int(round(width * SHADOW_BLUR_RATIO)))

    badges = []
    if score is not None:
        text = _format_score(score)
        color = _score_color(score) if score > 0 else SCORE_COLOR_UNRATED
        geometry = _badge_geometry(image.size, text, font, 'top-left', badge_height, min_width, radius, text_padding)
        badges.append((text, color, geometry))
    if age_rating:
        text = f"age {age_rating}"
        geometry = _badge_geometry(image.size, text, font, 'bottom-right', badge_height, min_width, radius, text_padding)
        badges.append((text, AGE_BADGE_BG, geometry))

    shadow_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    for _, _, geometry in badges:
        _draw_shadow(shadow_draw, geometry, shadow_y_offset)
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
