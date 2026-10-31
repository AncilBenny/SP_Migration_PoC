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
import re

MAX_IMAGE_BYTES = 5_000_000
MAX_PIXELS = 18_000_000
MAX_HEIGHT = 16_000
MAX_WIDTH = 3000
TILE = 256
DIFF_THRESHOLD = 24
MAX_COMPONENTS = 200
NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")


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



def _component_changes(maximum, components: list, *, viewport_width: int, shared_height: int,
                       target_height: int, threshold: int, node_mappings: list | None) -> dict:
    """Annotate changed pixels overlapping *target* node bounds, not source causes."""
    if not isinstance(components, list) or len(components) > MAX_COMPONENTS:
        raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID: expected <=200 components')
    component_types = {}
    if node_mappings is not None:
        if not isinstance(node_mappings, list) or len(node_mappings) > MAX_COMPONENTS:
            raise ValueError('VISUAL_COMPONENT_MAPPING_INVALID')
        for mapping in node_mappings:
            if not isinstance(mapping, dict):
                raise ValueError('VISUAL_COMPONENT_MAPPING_INVALID')
            key = mapping.get('nodeId')
            component = mapping.get('targetComponent')
            if not isinstance(key, str) or not NODE_ID.fullmatch(key):
                raise ValueError('VISUAL_COMPONENT_MAPPING_INVALID')
            if not isinstance(component,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,39}',component):
                raise ValueError('VISUAL_COMPONENT_MAPPING_INVALID')
            component_types[key]=component
    from PIL import Image, ImageDraw
    covered_mask=Image.new('L',maximum.size,0)
    draw_coverage=ImageDraw.Draw(covered_mask)
    rows = []
    seen = set()
    for item in components:
        if not isinstance(item,dict):
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID')
        node_id=item.get('nodeId')
        rect=item.get('rect')
        tag=item.get('elementTag')
        if (not isinstance(node_id,str) or not NODE_ID.fullmatch(node_id) or node_id in seen
            or not isinstance(rect,dict) or set(rect) != {'x','y','width','height'}
            or any(type(rect.get(k)) is not int or abs(rect[k])>100_000 for k in rect)
            or rect['width']<=0 or rect['height']<=0
            or not isinstance(tag,str) or tag not in {'div','section','article','header','nav','aside','figure','ul','ol','p','main'}):
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID')
        seen.add(node_id)
        x, y = rect['x'],rect['y']
        right, bottom=x+rect['width'],y+rect['height']
        left=max(0,x);top=max(0,y)
        clipped_right=min(viewport_width,right)
        clipped_bottom=min(shared_height,bottom)
        # Target pixels beyond the source screenshot height cannot be compared.
        unmatched_target_area = max(0,min(target_height,bottom)-max(shared_height,y)) * max(0,min(viewport_width,right)-max(0,x))
        changed=0; comparable=0
        if clipped_right>left and clipped_bottom>top:
            region=maximum.crop((left,top,clipped_right,clipped_bottom))
            draw_coverage.rectangle((left,top,clipped_right-1,clipped_bottom-1),fill=255)
            changed=sum(region.histogram()[threshold+1:])
            comparable=(clipped_right-left)*(clipped_bottom-top)
        if not comparable and not unmatched_target_area:
            continue
        kind=component_types.get(node_id)
        # These are review suggestions based only on the destination element
        # category, not guesses about which source CSS rule caused a difference.
        hint = ('Check image source, crop, intrinsic dimensions and container sizing' if kind=='media'
                else 'Check target spacing, typography and responsive breakpoint styles' if kind in ('contentBody','pageHeader')
                else 'Check card layout, padding and link presentation' if kind in ('resourceCards','simpleLinks')
                else 'Inspect target component geometry and computed styles')
        probe=item.get('styleProbe', {})
        if not isinstance(probe,dict) or any(not isinstance(v,str) or len(v)>80 for v in probe.values()) or len(probe)>6:
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID: style probe')
        rows.append({'nodeId':node_id,'targetComponent':kind,'elementTag':tag,
                     'targetStyleProbe':{k:probe[k] for k in ('fontSize','lineHeight','display') if k in probe},
                     'targetBounds':dict(rect),'comparedPixels':comparable,
                     'changedPixels':changed,
                     'changedFraction':round(changed/comparable,6) if comparable else None,
                     'unmatchedTargetPixels':unmatched_target_area,
                     'reviewHint':hint})
    outside=Image.composite(Image.new('L',maximum.size,0),maximum,covered_mask)
    unattributed=sum(outside.histogram()[threshold+1:])
    rows.sort(key=lambda row:(-row['changedPixels'],-row['unmatchedTargetPixels'],row['nodeId']))
    affected=[r for r in rows if r['changedPixels'] or r['unmatchedTargetPixels']]
    return {'mode':'target-geometry-overlap', 'capturedNodeCount':len(components),
            'reviewedNodeCount':len(rows), 'affectedNodeCount':len(affected),
            'unattributedChangedPixels':unattributed,
            'topAffectedNodes':affected[:30],
            'limitations':'Overlapping target component rectangles can count the same changed pixels more than once. Region overlap does NOT establish root cause or identify source CSS. Components absent from rendered destination have no geometry. No source DOM bounds were supplied.'}

def compare_screenshots(source_png: bytes, target_png: bytes, *, viewport_width: int,
                        threshold: int = DIFF_THRESHOLD, include_heatmap: bool = False,
                        components: list | None = None, node_mappings: list | None = None) -> tuple[dict, bytes | None]:
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
    if components is not None:
        result['componentDifferences'] = _component_changes(
            maximum, components, viewport_width=viewport_width,
            shared_height=h, target_height=target.height, threshold=threshold,
            node_mappings=node_mappings)
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


def compare_screenshot_files(source: Path, destination: Path, out_dir: Path, *, viewport_width: int, threshold: int = DIFF_THRESHOLD, browser_report: Path | None = None, mapping_report: Path | None = None) -> dict:
    source=Path(source);destination=Path(destination);out_dir=Path(out_dir)
    geometry=None
    node_mappings=None
    if browser_report is not None:
        if Path(browser_report).stat().st_size > 1_000_000:
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID: oversized browser report')
        audit=json.loads(Path(browser_report).read_text(encoding='utf-8'))
        view=next((v for v in audit.get('viewports',{}).values()
                   if v.get('viewportWidth')==viewport_width),None)
        if view is None or 'componentGeometry' not in view:
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_INVALID: matching capture metadata unavailable')
        # Check the png digest: geometry cannot be borrowed from a different capture.
        if sha256(destination.read_bytes()).hexdigest()!=view.get('sha256'):
            raise ValueError('VISUAL_COMPONENT_GEOMETRY_MISMATCH: target screenshot differs from audit')
        geometry=view['componentGeometry']
    if mapping_report is not None:
        if browser_report is None or Path(mapping_report).stat().st_size > 1_000_000:
            raise ValueError('VISUAL_COMPONENT_MAPPING_INVALID: browser evidence required')
        node_mappings=json.loads(Path(mapping_report).read_text(encoding='utf-8')).get('nodeMappings')
    report,heatmap=compare_screenshots(source.read_bytes(),destination.read_bytes(),viewport_width=viewport_width,threshold=threshold,include_heatmap=True,components=geometry,node_mappings=node_mappings)
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/'difference-heatmap.png').write_bytes(heatmap)
    # Source and destination screenshot bytes are NOT copied to the report dir.
    (out_dir/'visual-review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
