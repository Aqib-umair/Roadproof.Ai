"""Download the pinned ONNX research artifact and verify its checksum."""
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/"models"/"research-model.json").read_text())
    path = root/"models"/manifest["local_file"]
    url = f'https://huggingface.co/{manifest["repository"]}/resolve/{manifest["revision"]}/{manifest["file"]}'
    temporary = path.with_suffix(".partial")
    urllib.request.urlretrieve(url,temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=manifest["sha256"]:
        temporary.unlink(missing_ok=True)
        raise SystemExit("The downloaded model does not match the pinned checksum. It has not been installed.")
    temporary.replace(path)
    print("Pinned experimental ONNX model downloaded and checksum verified.")
    print("This is not local accuracy validation. See models/research-model.json and SETUP_SUPABASE_AI.md.")


if __name__ == "__main__":
    main()
