import csv, time
from pathlib import Path

class SessionAudit:
    def __init__(self):
        folder=Path.home()/"AppData"/"Local"/"QuotexVisionAI"/"sessions"
        folder.mkdir(parents=True,exist_ok=True)
        self.path=folder/f"session-{time.strftime('%Y%m%d-%H%M%S')}.csv"
        self.columns=["timestamp","event","track_id","state","direction","vision_confidence","tracking_age","tracking_stability","detection_quality","signal","up_score","down_score","signal_confidence","agreement","horizon_seconds"]
        with self.path.open("w",newline="",encoding="utf-8") as f:
            csv.DictWriter(f,fieldnames=self.columns).writeheader()
    def record(self,event,**values):
        row={c:"" for c in self.columns}
        row["timestamp"]=time.strftime("%Y-%m-%d %H:%M:%S")
        row["event"]=event
        for k,v in values.items():
            if k in row: row[k]=v
        try:
            with self.path.open("a",newline="",encoding="utf-8") as f:
                csv.DictWriter(f,fieldnames=self.columns).writerow(row)
        except OSError:
            pass
