#!/usr/bin/env bash
# Install (or repair) the YuE2 music engine used by the generate-music skill.
#
# Everything lives under $YUE2_HOME (default ~/engines/yue2); deleting that
# folder removes the engine completely. Safe to re-run: finished steps are skipped.
#
#   bash install_engine.sh            # install / verify
#   YUE2_HOME=/other/place bash install_engine.sh
set -euo pipefail

YUE2_HOME="${YUE2_HOME:-$HOME/engines/yue2}"
PYTHON="${PYTHON:-python3.12}"
YUE_REPO="https://github.com/multimodal-art-projection/YuE.git"
YUE_COMMIT="09a1e8a85bf35a93b8c01b3f12b139b558b49852"   # yue2-infer 0.1.6
MODEL_REV="14fc6c6f146441b1dd6363fcb2e01e82a6914cb7"    # m-a-p/YuE2-3B
VAE_REV="9a94e1d0ea9f8087e98f77fa88df4a4068104d2a"      # m-a-p/YuE2-Vae
DEMUCS_VERSION="4.1.0"
LIBROSA_VERSION="1.0.0"                                  # pitch/onset analysis

VENV="$YUE2_HOME/.venv"
VPY="$VENV/bin/python"
export HF_HOME="$YUE2_HOME/hf-home"
export TORCH_HOME="$YUE2_HOME/torch-home"
export HF_HUB_DISABLE_TELEMETRY=1

step() { printf '\n==> %s\n' "$*"; }

mkdir -p "$YUE2_HOME" "$HF_HOME" "$TORCH_HOME" "$YUE2_HOME/models"

step "1/6 YuE source at $YUE_COMMIT"
if [ ! -d "$YUE2_HOME/YuE/.git" ]; then
    git clone --quiet "$YUE_REPO" "$YUE2_HOME/YuE"
fi
if [ "$(git -C "$YUE2_HOME/YuE" rev-parse HEAD)" != "$YUE_COMMIT" ]; then
    git -C "$YUE2_HOME/YuE" fetch --quiet origin
    git -C "$YUE2_HOME/YuE" -c advice.detachedHead=false checkout --quiet "$YUE_COMMIT"
fi

step "2/6 Python venv and yue2-infer"
if [ ! -x "$VPY" ]; then
    "$PYTHON" -m venv "$VENV"
    "$VPY" -m pip install --quiet --upgrade pip
fi
if ! "$VPY" -c "import yue2" 2>/dev/null; then
    "$VPY" -m pip install --quiet "$YUE2_HOME/YuE"
    "$VPY" -m pip freeze --exclude-editable | grep -v '^yue2-infer' > "$YUE2_HOME/constraints.txt"
fi

step "3/6 Demucs $DEMUCS_VERSION + librosa (constrained so torch/numpy never move)"
if ! "$VPY" -c "import demucs, librosa" 2>/dev/null; then
    "$VPY" -m pip install --quiet -c "$YUE2_HOME/constraints.txt" "demucs==$DEMUCS_VERSION" "librosa==$LIBROSA_VERSION"
fi

step "4/6 GPU check"
"$VPY" - <<'EOF'
import torch
assert torch.cuda.is_available(), "CUDA not available to torch"
arch = torch.cuda.get_arch_list()
major, minor = torch.cuda.get_device_capability(0)
need = f"sm_{major}{minor}"
print(f"torch {torch.__version__} cuda {torch.version.cuda}; GPU {torch.cuda.get_device_name(0)} ({need}); arch {arch}")
assert need in arch, f"this torch build lacks {need}"
assert torch.cuda.is_bf16_supported(), "GPU lacks BF16"
EOF

step "5/6 Model weights (pinned revisions)"
"$VPY" - "$YUE2_HOME" "$MODEL_REV" "$VAE_REV" <<'EOF'
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
home, model_rev, vae_rev = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
for repo, rev in (("m-a-p/YuE2-3B", model_rev), ("m-a-p/YuE2-Vae", vae_rev)):
    target = home / "models" / repo.split("/")[1]
    snapshot_download(repo, revision=rev, local_dir=target,
                      ignore_patterns=["*.whl", "assets/*", "examples/*"])
    print("ok", repo, rev[:7], "->", target)
EOF
"$VPY" - <<'EOF'
from demucs.pretrained import get_model
get_model("htdemucs")
print("ok htdemucs")
EOF

step "6/6 Doctor, engine.json, INSTALLED.json"
YUE2_KIT="$YUE2_HOME" "$VENV/bin/yue2" doctor --offline --verify-hashes --output "$YUE2_HOME/doctor.json" > /dev/null
if [ ! -f "$YUE2_HOME/engine.json" ]; then
    cat > "$YUE2_HOME/engine.json" <<'EOF'
{
  "memory_budget_gib": 16,
  "offload_ar": false,
  "quantization": "none",
  "backend": "torch",
  "demucs_model": "htdemucs"
}
EOF
fi
"$VPY" - "$YUE2_HOME" "$YUE_COMMIT" "$MODEL_REV" "$VAE_REV" <<'EOF'
import datetime, importlib.metadata as md, json, sys
from pathlib import Path
home = Path(sys.argv[1])
doctor = json.loads((home / "doctor.json").read_text())
info = {
    "installed": datetime.datetime.now().isoformat(timespec="seconds"),
    "yue_commit": sys.argv[2],
    "model": {"repo": "m-a-p/YuE2-3B", "revision": sys.argv[3], "path": str(home / "models/YuE2-3B")},
    "vae": {"repo": "m-a-p/YuE2-Vae", "revision": sys.argv[4], "path": str(home / "models/YuE2-Vae")},
    "packages": {p: md.version(p) for p in ("yue2-infer", "torch", "transformers", "numpy", "demucs", "librosa", "soundfile")},
    "cuda": doctor.get("cuda"),
    "weights": doctor.get("weights"),
}
(home / "INSTALLED.json").write_text(json.dumps(info, indent=2) + "\n")
print(json.dumps(info["packages"]), "\nweights verified:", bool(info["weights"]))
EOF
printf '\nEngine ready at %s\n' "$YUE2_HOME"
