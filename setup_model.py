"""Download the official model through the local Ollama API with readable progress."""
import json
import sys
import urllib.request

if __name__ == "__main__":
    req = urllib.request.Request("http://127.0.0.1:11434/api/pull",
        data=json.dumps({"model": "translategemma:12b", "stream": True}).encode(),
        headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    previous, success = None, False
    try:
        with opener.open(req, timeout=600) as response:
            for line in response:
                event = json.loads(line)
                if "error" in event:
                    raise RuntimeError(event["error"])
                status = event.get("status", "")
                percent = int(100 * event.get("completed", 0) / event["total"]) if event.get("total") else None
                key = (status, percent // 5 if percent is not None else None)
                if key != previous:
                    print(status + (f" {percent}%" if percent is not None else ""), flush=True)
                    previous = key
                success = status == "success"
        if not success:
            raise RuntimeError("Download ended without confirmation")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
