"""Render the demo CLI output to docs/demo.png (needs google-chrome)."""
import html, os, re, subprocess, sys, tempfile

CODES = {"1": "font-weight:700", "2": "opacity:.55", "91": "color:#ff6b6b", "92": "color:#5af78e",
         "93": "color:#f4d35e", "94": "color:#6cb6ff", "95": "color:#d6a0ff", "96": "color:#57e3e3"}
env = dict(os.environ, FORCE_COLOR="1")
raw = subprocess.run([sys.executable, "-m", "contextboss.cli", "--budget", "680"], env=env,
                     capture_output=True, text=True, check=True).stdout
out, open_spans = [], 0
for part in re.split(r"(\x1b\[[0-9;]*m)", html.escape(raw)):
    m = re.fullmatch(r"\x1b\[([0-9;]*)m", part)
    if not m:
        out.append(part); continue
    if m.group(1) == "0":
        out.append("</span>" * open_spans); open_spans = 0
    else:
        out.append(f'<span style="{CODES.get(m.group(1), "")}">'); open_spans += 1
body = "".join(out) + "</span>" * open_spans
page = f"""<html><body style="margin:0;background:linear-gradient(135deg,#1b1035,#0b1d3a);padding:48px 48px 60px">
<div style="width:1080px;margin:auto;border-radius:14px;background:#0d1117;box-shadow:0 30px 80px #000a;overflow:hidden;font-family:'DejaVu Sans Mono',monospace">
<div style="background:#161b22;padding:12px 16px;display:flex;gap:8px;align-items:center">
<i style="width:12px;height:12px;border-radius:6px;background:#ff5f56"></i><i style="width:12px;height:12px;border-radius:6px;background:#ffbd2e"></i><i style="width:12px;height:12px;border-radius:6px;background:#27c93f"></i>
<span style="color:#8b949e;font-size:13px;margin-left:12px">~/contextboss  $ contextboss --budget 680</span></div>
<pre style="margin:0;padding:22px 26px;color:#e6edf3;font-size:14px;line-height:1.5">{body}</pre></div></body></html>"""
with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
    f.write(page)
subprocess.run(["google-chrome", "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=2", "--window-size=1180,900", f"--screenshot=docs/demo.png",
                "file://" + f.name], check=True, capture_output=True)
print("wrote docs/demo.png")
