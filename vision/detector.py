from dataclasses import dataclass
import cv2, numpy as np
from .models import Candle, Detection

@dataclass
class DetectorConfig:
    min_candles: int = 10
    max_candles: int = 30
    min_body_width_px: int = 2

class CandleDetector:
    def __init__(self, config=None, max_candles=None, min_body_width=2):
        if isinstance(config, DetectorConfig):
            self.min_candles = config.min_candles
            self.max_candles = config.max_candles
            self.min_body_width = config.min_body_width_px
        else:
            self.min_candles = 10 if config is None else int(config)
            self.max_candles = 30 if max_candles is None else int(max_candles)
            self.min_body_width = int(min_body_width)

    def detect(self, frame_bgr, roi_norm):
        h,w=frame_bgr.shape[:2]
        l,t,r,b=[int(v) for v in (w*roi_norm[0],h*roi_norm[1],w*roi_norm[2],h*roi_norm[3])]
        crop=frame_bgr[t:b,l:r]
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        red=cv2.bitwise_or(cv2.inRange(hsv,np.array([0,70,70],np.uint8),np.array([12,255,255],np.uint8)),cv2.inRange(hsv,np.array([165,70,70],np.uint8),np.array([179,255,255],np.uint8)))
        green=cv2.inRange(hsv,np.array([35,55,55],np.uint8),np.array([95,255,255],np.uint8))
        orange=cv2.inRange(hsv,np.array([10,70,70],np.uint8),np.array([35,255,255],np.uint8))
        colored=cv2.bitwise_or(cv2.bitwise_or(red,green),orange)
        colored=cv2.morphologyEx(colored,cv2.MORPH_OPEN,np.ones((2,2),np.uint8))
        score=(colored>0).sum(axis=0).astype(np.float32); score=cv2.GaussianBlur(score.reshape(1,-1),(1,0),0).reshape(-1)
        th=max(4.0,float(np.percentile(score,68))*0.55); active=score>=th; groups=[]; s=None
        for x,on in enumerate(active):
            if on and s is None: s=x
            elif not on and s is not None:
                if x-s>=self.min_body_width: groups.append((s,x-1))
                s=None
        if s is not None and len(active)-s>=self.min_body_width: groups.append((s,len(active)-1))
        groups=self._merge(groups)
        refined=[]
        expected=max(4,int(crop.shape[1]/max(10,self.max_candles)))
        for a,z in groups:
            width=z-a+1
            n=max(1,int(round(width/expected))) if width>expected*2 else 1
            sw=width/n
            for i in range(n):
                aa=int(round(a+i*sw)); zz=int(round(a+(i+1)*sw-1));
                if zz-aa+1>=self.min_body_width: refined.append((aa,zz))
        refined=sorted(refined)
        if len(refined)>self.max_candles: refined=refined[-self.max_candles:]
        candles=[]
        for a,z in refined:
            loc=colored[:,a:z+1]; ys,_=np.where(loc>0)
            if len(ys)<8: continue
            y0,y1=int(ys.min()),int(ys.max()); yp=(loc>0).sum(axis=1); nz=yp[yp>0]
            cut=max(1,int(np.percentile(nz,55))); body_rows=np.where(yp>=cut)[0]
            bt,bb=(int(body_rows.min()),int(body_rows.max())) if len(body_rows) else (y0,y1)
            cx=(a+z)//2; cl=max(0,cx-3); cr=min(colored.shape[1]-1,cx+3); wcol=colored[:,cl:cr+1]; wy=np.where(wcol>0)[0]
            high,low=(float(wy.min()),float(wy.max())) if len(wy) else (float(y0),float(y1))
            rc=int(np.count_nonzero(red[:,a:z+1])); gc=int(np.count_nonzero(green[:,a:z+1])); bull=gc>=rc
            op=float(bb if bull else bt); cp=float(bt if bull else bb)
            dens=min(1.0,len(ys)/max(1,(z-a+1)*max(1,y1-y0+1)*0.55)); conf=min(1.0,0.45+0.35*dens+0.20*min(1.0,(z-a+1)/8.0))
            candles.append(Candle(cx+l,a+l,z+l,bt+t,bb+t,high+t,low+t,op+t,cp+t,bull,len(ys),conf))
        if candles:
            for c in candles:
                c.is_current = False
            candles[-1].is_current = True

        quality=self._quality(candles)
        msg=(f"{len(candles)} candles detected. Vision locked." if len(candles)>=self.min_candles and quality>=0.6 else f"Only {len(candles)} candles detected. Put the overlay ROI on the plot area.")
        return Detection(
            candles=candles,
            quality=quality,
            message=msg,
            roi=(l,t,r,b),
            current_index=(len(candles)-1 if candles else -1),
            current_price_y=(candles[-1].close_px if candles else None),
            price_proxy_ready=bool(candles),
        )

    def _merge(self, groups):
        out=[]
        for g in groups:
            if not out: out.append(g); continue
            a,z=out[-1]
            if g[0]-z-1<=2: out[-1]=(a,g[1])
            else: out.append(g)
        return out

    def _quality(self,candles):
        if not candles:return 0.0
        count=min(1.0,len(candles)/15.0); conf=float(np.mean([c.confidence for c in candles])); spacing=[candles[i+1].x_center-candles[i].x_center for i in range(len(candles)-1)]
        if len(spacing)>=3:
            med=float(np.median(spacing)); dev=float(np.mean([abs(x-med) for x in spacing])); sp=max(0.0,1.0-dev/max(1.0,med*.8))
        else: sp=0.0
        return float(max(0.0,min(1.0,0.40*count+0.35*conf+0.25*sp)))
