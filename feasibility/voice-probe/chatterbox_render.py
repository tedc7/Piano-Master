"""Trial: render lesson lines with Chatterbox's built-in voice."""
import json, sys, time
import soundfile as sf
from chatterbox.tts import ChatterboxTTS
lines = json.load(open("lines.json"))
exag, cfg, tag = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
model = ChatterboxTTS.from_pretrained(device="cuda")
t0 = time.time(); total = 0.0
for l in lines:
    wav = model.generate(l.get("say_plain") or l["text"], exaggeration=exag, cfg_weight=cfg)
    total += wav.shape[-1] / model.sr
    sf.write(f"out/chatterbox-{tag}-{l['id']}.wav", wav.squeeze(0).cpu().numpy(), model.sr)
print(f"chatterbox {tag}: {total:.1f} s of speech in {time.time() - t0:.1f} s")
