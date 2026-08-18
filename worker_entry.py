from worker_runtime import run_self_test, run_worker
import argparse

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--port",type=int,default=0)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--self-test-seconds",type=int,default=10)
    a=p.parse_args()
    if a.self_test:
        raise SystemExit(run_self_test(a.self_test_seconds))
    if a.port<=0:
        raise SystemExit("Worker requires --port")
    raise SystemExit(run_worker(a.host,a.port))
