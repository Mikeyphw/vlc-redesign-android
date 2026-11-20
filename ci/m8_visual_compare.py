#!/usr/bin/env python3
"""M8 visual-diff gate. Requires approved baseline screenshots and Pillow on a hosted/desktop runner.

Not a substitute for device QA. Never invent or auto-approve reference images.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    p=argparse.ArgumentParser(description='Compare approved M8 baseline and current screenshots')
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--actual',type=Path,required=True)
    p.add_argument('--max-changed-percent',type=float,default=1.0)
    p.add_argument('--max-mean-error',type=float,default=3.0)
    p.add_argument('--pixel-tolerance',type=int,default=8)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not all((a.baseline.is_file(),a.actual.is_file())):
        p.error('both baseline and actual must exist; no synthesized/auto-approved baseline')
    if not (0 <= a.max_changed_percent <= 100 and 0 <= a.max_mean_error <= 255 and 0 <= a.pixel_tolerance <= 255):
        p.error('invalid thresholds')
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        print('M8_VISUAL_INCOMPLETE: Pillow unavailable (install on hosted/desktop runner)',file=sys.stderr)
        return 2
    with Image.open(a.baseline) as base_im, Image.open(a.actual) as actual_im:
        if base_im.size != actual_im.size:
            print('M8_VISUAL_FAIL screenshot dimensions differ '+str(base_im.size)+' vs '+str(actual_im.size),file=sys.stderr)
            return 1
        base=base_im.convert('RGB');actual=actual_im.convert('RGB')
        diff=ImageChops.difference(base,actual)
        # Pixel changed when *any* color channel exceeds tolerance.
        changed=0; error=0; total=base.width*base.height
        for r,g,b in diff.getdata():
            changed += (max(r,g,b)>a.pixel_tolerance)
            error += r+g+b
        pct=100.0*changed/total
        mean=error/(3*total)
        verdict='PASS' if pct<=a.max_changed_percent and mean<=a.max_mean_error else 'FAIL'
        result={'verdict':verdict,'baseline':str(a.baseline),'actual':str(a.actual),
                'size':list(base.size),'changed_percent':round(pct,4),'mean_error':round(mean,4),
                'thresholds':{'max_changed_percent':a.max_changed_percent,
                              'max_mean_error':a.max_mean_error,'pixel_tolerance':a.pixel_tolerance}}
        output=json.dumps(result,indent=2)+'\n'
        print(output,end='',flush=True)
        if a.output:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(output,encoding='utf-8')
        return 0 if verdict=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
