"""Evidence-limited screenshot comparison for manually supplied page baselines.

No source site access, script evaluation, or image uploads. Differencing is a
review signal only: anti-aliasing, fonts, dynamic data, consent and viewport
settings can cause differences without content loss. Never claims parity.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json

MAX_IMAGE_BYTES = 5_000_000
MAX_PIXELS = 18_000_000
MAX_HEIGHT = 16_000
MAX_WIDTH = 3000
TILE = 256
DIFF_THRESHOLD = 24


def _decode_png(raw: bytes):
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError('VISUAL_REVIEW_REQUIRES_PILLOW: pip install pillow') from exc
    if not isinstance(raw, bytes) or not (60 <= len(raw) <= MAX_IMAGE_BYTES):
        raise ValueError('VISUAL_IMAGE_LIMIT: PNG must be 60 bytes to 5 MB')
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('VISUAL_IMAGE_FORMAT: PNG screenshots only')
    try:
        with Image.open(BytesIO(raw)) as img:
            if img.format != 'PNG' or img.n_frames != 1:
                raise ValueError('VISUAL_IMAGE_FORMAT: single-frame PNG required')
            w,h=img.size
            if not (100 <= w <= MAX_WIDTH and 100 <= h <= MAX_HEIGHT and w*h <= MAX_PIXELS):
                raise ValueError('VISUAL_IMAGE_LIMIT: dimensions or decompressed pixels exceed review limits')
            img.load()
            return img.convert('RGB')
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError('VISUAL_IMAGE_INVALID: cannot decode PNG') from exc


def compare_screenshots(source_png: bytes, target_png: bytes, *, viewport_width: int,
                        threshold: int = DIFF_THRESHOLD, include_heatmap: bool = False) -> tuple[dict, bytes | None]:
    """Compare source and destination raster evidence using unscaled pixels.

    Both images must represent the *same* viewport width; full-page screenshot
    height can differ. A different height is surfaced rather than cropped away.
    The original source screenshot is never returned or retained in the report.
    """
    if type(viewport_width) is not int or viewport_width not in (390, 768, 1024, 1440):
        raise ValueError('VISUAL_VIEWPORT_INVALID: supported widths are 390, 768, 1024, 1440')
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError('VISUAL_THRESHOLD_INVALID')
    from PIL import Image, ImageChops, ImageDraw, ImageStat
    source = _decode_png(source_png)
    target = _decode_png(target_png)
    if source.width != viewport_width or target.width != viewport_width:
        raise ValueError('VISUAL_VIEWPORT_MISMATCH: source and destination PNG widths must equal the declared viewport')
    h=min(source.height,target.height)
    max_h=max(source.height,target.height)
    src_common=source.crop((0,0,viewport_width,h))
    tgt_common=target.crop((0,0,viewport_width,h))
    rgb_diff=ImageChops.difference(src_common,tgt_common)
    bands=rgb_diff.split()
    maximum=ImageChops.lighter(ImageChops.lighter(bands[0],bands[1]),bands[2])
    histogram=maximum.histogram()
    changed=sum(histogram[threshold+1:])
    shared_pixels=viewport_width*h
    total_pixels=viewport_width*max_h
    unmatched_pixels=total_pixels-shared_pixels
    # The combined difference fraction includes unmatched rows as review risk,
    # but exposes separate overlap/geometry percentages to avoid misleading users.
    hotspots=[]
    for top in range(0,h,TILE):
        for left in range(0,viewport_width,TILE):
            right,bottom=min(viewport_width,left+TILE),min(h,top+TILE)
            region=maximum.crop((left,top,right,bottom))
            count=sum(region.histogram()[threshold+1:])
            area=(right-left)*(bottom-top)
            if count:
                hotspots.append({'x':left,'y':top,'width':right-left,'height':bottom-top,
                                 'changedFraction':round(count/area,4),'changedPixels':count})
    hotspots.sort(key=lambda item:(-item['changedPixels'],item['y'],item['x']))
    box=maximum.point(lambda value:255 if value>threshold else 0).getbbox()
    mean_error=ImageStat.Stat(maximum).mean[0]
    result={
        'version':'visual-review-0.1',
        'comparison':'unscaled-aligned-pixel-difference',
        'sourceBaseline':'operator-supplied-png-unverified',
        'destinationCapture':'supplied-png-capture-method-not-independently-verified',
        'sourceBaselineVerified':False, 'sourceWebsiteContacted':False,
        'viewportWidth':viewport_width, 'threshold':threshold,
        'sourceImage':{'width':source.width,'height':source.height,'sha256':sha256(source_png).hexdigest()},
        'destinationImage':{'width':target.width,'height':target.height,'sha256':sha256(target_png).hexdigest()},
        'geometry':{'sameDimensions':source.size==target.size,
                    'unmatchedVerticalPixels':abs(source.height-target.height),
                    'unmatchedFraction':round(unmatched_pixels/total_pixels,6)},
        'pixelDifferences':{'overlapPixels':shared_pixels,'changedOverlapPixels':changed,
                            'changedOverlapFraction':round(changed/shared_pixels,6),
                            'meanMaximumChannelDelta':round(mean_error,3),
                            'combinedChangedOrUnmatchedFraction':round((changed+unmatched_pixels)/total_pixels,6),
                            'changedBoundingBox':list(box) if box else None,
                            'largestChangedTiles':hotspots[:10]},
        'fidelity':'not-verified-human-review-required',
        'releaseApproved':False,
        'reviewRequired':True,
        'interpretation':'Screen pixel differences are evidence for review, not a semantic, behavioral, accessibility, or full SharePoint fidelity test.',
    }
    heatmap = None
    if include_heatmap:
        output=Image.new('RGB',(viewport_width,max_h),'#f0f0f0')
        output.paste(target,(0,0))
        red=Image.new('RGB',(viewport_width,h),(232,59,70))
        mask=maximum.point(lambda value:180 if value>threshold else 0)
        output.paste(red,(0,0,viewport_width,h),mask)
        if max_h>h:
            draw=ImageDraw.Draw(output)
            draw.rectangle((0,h,viewport_width-1,max_h-1),fill=(236,184,48))
        buffer=BytesIO();output.save(buffer,format='PNG',optimize=True)
        heatmap=buffer.getvalue()
    return result, heatmap


def compare_screenshot_files(source: Path, destination: Path, out_dir: Path, *, viewport_width: int, threshold: int = DIFF_THRESHOLD) -> dict:
    source=Path(source);destination=Path(destination);out_dir=Path(out_dir)
    report,heatmap=compare_screenshots(source.read_bytes(),destination.read_bytes(),viewport_width=viewport_width,threshold=threshold,include_heatmap=True)
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/'difference-heatmap.png').write_bytes(heatmap)
    # Source and destination screenshot bytes are NOT copied to the report dir.
    (out_dir/'visual-review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
