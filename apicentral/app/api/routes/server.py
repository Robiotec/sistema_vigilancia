import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["server"])

_CPU_LOCK = threading.Lock()
_CPU_SNAPSHOT: dict[str, tuple[int, int]] | None = None


def _read_cpu_totals() -> dict[str, tuple[int, int]]:
    try:
        lines = Path("/proc/stat").read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}

    totals: dict[str, tuple[int, int]] = {}
    for line in lines:
        parts = line.split()
        if not parts or parts[0] != "cpu" and not parts[0].startswith("cpu"):
            continue
        if parts[0] != "cpu" and not parts[0][3:].isdigit():
            continue
        try:
            values = [int(value) for value in parts[1:]]
        except ValueError:
            continue
        if len(values) < 4:
            continue
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        totals[parts[0]] = (idle, sum(values))
    return totals


def _cpu_percentages() -> dict[str, Any]:
    global _CPU_SNAPSHOT
    current = _read_cpu_totals()
    if not current:
        return {"used_percent": None, "core_usage": []}

    with _CPU_LOCK:
        previous = _CPU_SNAPSHOT
        if previous is None:
            _CPU_SNAPSHOT = current
            time.sleep(0.08)
            current = _read_cpu_totals()
            previous = _CPU_SNAPSHOT
        _CPU_SNAPSHOT = current

    if not previous:
        return {"used_percent": None, "core_usage": []}

    usage: dict[str, float] = {}
    for name, (idle, total) in current.items():
        if name not in previous:
            continue
        prev_idle, prev_total = previous[name]
        total_delta = total - prev_total
        idle_delta = idle - prev_idle
        if total_delta <= 0:
            usage[name] = 0.0
        else:
            usage[name] = round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 2)

    core_usage = []
    core_names = sorted(
        [name for name in usage if name.startswith("cpu") and name[3:].isdigit()],
        key=lambda value: int(value[3:]),
    )
    for name in core_names:
        index = int(name[3:])
        core_usage.append({"name": f"C{index}", "linux_name": name, "used_percent": usage[name]})

    return {"used_percent": usage.get("cpu"), "core_usage": core_usage}


def _meminfo() -> dict[str, int]:
    data: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
    for line in lines:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        amount = raw_value.strip().split()[0]
        if amount.isdigit():
            data[key] = int(amount) * 1024
    return data


def _memory() -> dict[str, Any]:
    data = _meminfo()
    total = data.get("MemTotal", 0)
    available = data.get("MemAvailable", 0)
    used = max(0, total - available) if total else 0
    swap_total = data.get("SwapTotal", 0)
    swap_free = data.get("SwapFree", 0)
    swap_used = max(0, swap_total - swap_free) if swap_total else 0
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "used_percent": round((used / total) * 100, 2) if total else None,
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "swap_used_bytes": swap_used,
        "swap_used_percent": round((swap_used / swap_total) * 100, 2) if swap_total else None,
    }


def _disk(path: str, label: str | None = None) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except Exception:
        return {
            "path": path,
            "label": label or path,
            "exists": Path(path).exists(),
            "total_bytes": 0,
            "used_bytes": 0,
            "free_bytes": 0,
            "used_percent": None,
        }
    return {
        "path": path,
        "label": label or path,
        "exists": True,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round((usage.used / usage.total) * 100, 2) if usage.total else None,
    }


def _mounted_efi_paths() -> list[str]:
    paths: list[str] = []
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []

    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        mountpoint = parts[1].replace("\\040", " ")
        filesystem = parts[2].lower()
        lower_mountpoint = mountpoint.lower()
        if mountpoint in {"/boot/efi", "/efi"} or ("efi" in lower_mountpoint and filesystem in {"vfat", "fat", "msdos"}):
            paths.append(mountpoint)

    for candidate in ("/boot/efi", "/efi"):
        if Path(candidate).exists():
            paths.append(candidate)

    unique_paths = []
    for path in paths:
        if path not in unique_paths:
            unique_paths.append(path)
    return unique_paths


def _storage() -> dict[str, Any]:
    efi_paths = _mounted_efi_paths()
    disks = [_disk("/", "Sistema"), _disk("/root/robiotec", "Robiotec")]
    disks.extend(_disk(path, "EFI") for path in efi_paths if path not in {"/", "/root/robiotec"})
    return {
        "disk": disks,
        "efi": {
            "mounted": bool(efi_paths),
            "mounts": [_disk(path, "EFI") for path in efi_paths],
        },
    }


def _uptime() -> float | None:
    try:
        return round(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]), 2)
    except Exception:
        return None


def _network() -> dict[str, Any]:
    total_rx = 0
    total_tx = 0
    interfaces = []
    try:
        lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
    except Exception:
        lines = []
    for line in lines:
        if ":" not in line:
            continue
        name, payload = line.split(":", 1)
        fields = payload.split()
        if len(fields) < 16:
            continue
        rx = int(fields[0])
        tx = int(fields[8])
        total_rx += rx
        total_tx += tx
        interfaces.append({"name": name.strip(), "rx_bytes": rx, "tx_bytes": tx})
    return {"rx_bytes": total_rx, "tx_bytes": total_tx, "interfaces": interfaces}


def _temperatures() -> list[dict[str, Any]]:
    values = []
    for temp_file in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            celsius = round(int(temp_file.read_text(encoding="utf-8").strip()) / 1000, 1)
        except Exception:
            continue
        label = temp_file.parent.name
        try:
            label = (temp_file.parent / "type").read_text(encoding="utf-8").strip() or label
        except Exception:
            pass
        values.append({"name": label, "celsius": celsius})
    return values


def _processes() -> dict[str, Any]:
    watched = {
        "api_central": ["uvicorn", "apicentral"],
        "dashboard": ["uvicorn", "dashboard"],
        "mediamtx": ["mediamtx"],
        "postgres": ["postgres"],
    }
    services = {name: {"running": False, "count": 0} for name in watched}
    count = 0
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        count += 1
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore").lower()
        except Exception:
            continue
        for name, needles in watched.items():
            if all(needle in cmdline for needle in needles):
                services[name]["running"] = True
                services[name]["count"] += 1
    return {"process_count": count, "services": services}


def _server_payload() -> dict[str, Any]:
    load_avg = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
    storage = _storage()
    cpu = _cpu_percentages()
    return {
        "timestamp": int(time.time()),
        "hostname": os.uname().nodename if hasattr(os, "uname") else "",
        "uptime_seconds": _uptime(),
        "cpu": {
            "cores": os.cpu_count() or 0,
            "used_percent": cpu["used_percent"],
            "core_usage": cpu["core_usage"],
            "load_avg_1m": load_avg[0],
            "load_avg_5m": load_avg[1],
            "load_avg_15m": load_avg[2],
        },
        "memory": _memory(),
        "disk": storage["disk"],
        "efi": storage["efi"],
        "network": _network(),
        "temperatures": _temperatures(),
        "processes": _processes(),
    }


@router.get("/server")
def server_page(request: Request):
    if request.query_params.get("format") == "json":
        return JSONResponse(_server_payload())

    return HTMLResponse(
        """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ROBIOTEC Server</title>
  <style>
    :root{color-scheme:dark;--accent:#f13811;--good:#20d684;--warn:#f59e0b;--panel:#161616;--panel2:#202020;--line:rgba(255,255,255,.1);--text:#fff;--muted:rgba(255,255,255,.66)}
    *{box-sizing:border-box}
    body{margin:0;min-height:100vh;background:linear-gradient(180deg,#252525,#0f0f0f);color:var(--text);font-family:Manrope,Segoe UI,Arial,sans-serif}
    main{display:grid;gap:16px;padding:22px}
    .hero,.card{border:1px solid var(--line);border-radius:14px;background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.018)),var(--panel);box-shadow:0 22px 48px rgba(0,0,0,.28)}
    .hero{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;padding:18px}
    h1{margin:0;font-size:clamp(1.45rem,3vw,2.4rem)}
    p{margin:5px 0 0;color:var(--muted)}
    .pill{border:1px solid rgba(20,184,166,.34);border-radius:999px;padding:9px 12px;color:#99f6e4;font-size:.76rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}
    .card{min-height:152px;padding:16px}
    .wide{grid-column:span 2}
    .full{grid-column:1/-1}
    h2{margin:0 0 12px;color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.14em}
    .value{display:block;margin-bottom:8px;font-size:clamp(1.55rem,2.8vw,2.35rem);font-weight:900;line-height:1}
    .meta,.list{color:var(--muted);font-size:.9rem;line-height:1.5}
    .bar{height:9px;overflow:hidden;border-radius:99px;background:rgba(255,255,255,.08)}
    .bar span{display:block;width:var(--value,0%);height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--good),var(--warn),var(--accent));transition:width .28s ease}
    .list{display:grid;gap:8px;margin:0;padding:0;list-style:none}
    .list li{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.08)}
    .list li:last-child{border-bottom:0}
    .list strong{color:var(--text);font-size:.9rem;text-align:right}
    .dot{display:inline-block;width:9px;height:9px;border-radius:99px;background:#ef4444;box-shadow:0 0 0 4px rgba(239,68,68,.12)}
    .dot.on{background:var(--good);box-shadow:0 0 0 4px rgba(32,214,132,.12)}
    .sparks{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
    .spark{min-width:0;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.03);padding:12px}
    .spark-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;color:var(--muted);font-size:.74rem;font-weight:900;text-transform:uppercase;letter-spacing:.1em}
    canvas{display:block;width:100%;height:112px}
    @media(max-width:1180px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.sparks{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:680px){main{padding:12px}.hero{align-items:flex-start;flex-direction:column}.grid,.sparks{grid-template-columns:1fr}.wide{grid-column:auto}}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div>
        <h1 id="host">Servidor</h1>
        <p id="summary">CPU, C0/C1, RAM, swap, EFI, red y servicios.</p>
      </div>
      <span class="pill" id="updated">Actualizando</span>
    </section>
    <section class="grid">
      <article class="card"><h2>CPU</h2><span class="value" id="cpu">--%</span><div class="bar"><span id="cpuBar"></span></div><p class="meta" id="cpuMeta">--</p></article>
      <article class="card"><h2>C0 / C1</h2><ul class="list" id="cores"></ul></article>
      <article class="card"><h2>RAM</h2><span class="value" id="ram">--%</span><div class="bar"><span id="ramBar"></span></div><p class="meta" id="ramMeta">--</p></article>
      <article class="card"><h2>Swap</h2><span class="value" id="swap">--%</span><div class="bar"><span id="swapBar"></span></div><p class="meta" id="swapMeta">--</p></article>
      <article class="card"><h2>Uptime</h2><span class="value" id="uptime">--</span><p class="meta" id="processes">-- procesos</p></article>
      <article class="card"><h2>Red</h2><span class="value" id="net">--</span><p class="meta" id="netMeta">RX -- · TX --</p></article>
      <article class="card"><h2>EFI</h2><span class="value" id="efi">--</span><p class="meta" id="efiMeta">--</p></article>
      <article class="card"><h2>Temperatura</h2><ul class="list" id="temps"></ul></article>
      <article class="card wide"><h2>Disco</h2><ul class="list" id="disk"></ul></article>
      <article class="card wide"><h2>Servicios</h2><ul class="list" id="services"></ul></article>
      <article class="card wide"><h2>Interfaces</h2><ul class="list" id="ifaces"></ul></article>
      <article class="card wide"><h2>Carga</h2><ul class="list" id="loads"></ul></article>
      <article class="card full">
        <h2>Curvas</h2>
        <div class="sparks">
          <div class="spark"><div class="spark-head"><span>CPU</span><strong id="cpuNow">--%</strong></div><canvas id="chartCpu"></canvas></div>
          <div class="spark"><div class="spark-head"><span>RAM</span><strong id="ramNow">--%</strong></div><canvas id="chartRam"></canvas></div>
          <div class="spark"><div class="spark-head"><span>Swap</span><strong id="swapNow">--%</strong></div><canvas id="chartSwap"></canvas></div>
          <div class="spark"><div class="spark-head"><span>Red</span><strong id="netNow">--/s</strong></div><canvas id="chartNet"></canvas></div>
        </div>
      </article>
    </section>
  </main>
  <script>
    const history={cpu:[],ram:[],swap:[],net:[]};
    let previousNetwork=null;
    const maxPoints=80;
    const bytes=(v)=>{v=Number(v);if(!Number.isFinite(v)||v<=0)return"--";const u=["B","KB","MB","GB","TB"];let i=0;while(v>=1024&&i<u.length-1){v/=1024;i++}return`${v>=100?v.toFixed(0):v.toFixed(1)} ${u[i]}`};
    const rate=(v)=>`${bytes(v)}/s`;
    const pct=(v)=>Number.isFinite(Number(v))?`${Number(v).toFixed(Number(v)>=10?1:2)}%`:"--%";
    const up=(s)=>{s=Number(s);if(!Number.isFinite(s))return"--";const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return d?`${d}d ${h}h`:h?`${h}h ${m}m`:`${m}m`};
    const bar=(id,v)=>document.getElementById(id).style.setProperty("--value",`${Math.max(0,Math.min(100,Number(v)||0))}%`);
    const list=(id,items)=>{const el=document.getElementById(id);el.innerHTML="";(items.length?items:["Sin datos"]).forEach(item=>{const li=document.createElement("li");if(typeof item==="string")li.textContent=item;else li.innerHTML=item;el.appendChild(li)})};
    const push=(key,value)=>{value=Number(value);if(!Number.isFinite(value))value=0;history[key].push(value);if(history[key].length>maxPoints)history[key].shift()};
    const labels={api_central:"API central",dashboard:"Dashboard",mediamtx:"MediaMTX",postgres:"PostgreSQL"};
    function draw(id,values,color,limit=100){const canvas=document.getElementById(id),dpr=window.devicePixelRatio||1,rect=canvas.getBoundingClientRect(),w=Math.max(1,rect.width),h=Math.max(1,rect.height);if(canvas.width!==Math.floor(w*dpr)||canvas.height!==Math.floor(h*dpr)){canvas.width=Math.floor(w*dpr);canvas.height=Math.floor(h*dpr)}const ctx=canvas.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.strokeStyle="rgba(255,255,255,.08)";ctx.lineWidth=1;for(let i=1;i<4;i++){const y=h*i/4;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}if(values.length<2)return;const max=Math.max(limit,...values,1);ctx.beginPath();values.forEach((v,i)=>{const x=i*(w/(maxPoints-1));const y=h-(Math.max(0,Math.min(max,v))/max)*h;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.strokeStyle=color;ctx.lineWidth=2.4;ctx.stroke()}
    async function refresh(){try{const r=await fetch("/server?format=json",{cache:"no-store",headers:{Accept:"application/json"}});const d=await r.json();document.getElementById("host").textContent=d.hostname||"Servidor";document.getElementById("updated").textContent=new Date((d.timestamp||Date.now()/1000)*1000).toLocaleTimeString();document.getElementById("summary").textContent=`Uptime ${up(d.uptime_seconds)} · ${d.cpu.cores||0} núcleos · ${d.processes.process_count||0} procesos`;
    document.getElementById("cpu").textContent=pct(d.cpu.used_percent);bar("cpuBar",d.cpu.used_percent);document.getElementById("cpuMeta").textContent=`carga ${Number(d.cpu.load_avg_1m||0).toFixed(2)} / ${Number(d.cpu.load_avg_5m||0).toFixed(2)} / ${Number(d.cpu.load_avg_15m||0).toFixed(2)}`;list("cores",(d.cpu.core_usage||[]).map(x=>`<span>${x.name}</span><strong>${pct(x.used_percent)}</strong>`));
    document.getElementById("ram").textContent=pct(d.memory.used_percent);bar("ramBar",d.memory.used_percent);document.getElementById("ramMeta").textContent=`${bytes(d.memory.used_bytes)} usado de ${bytes(d.memory.total_bytes)}`;document.getElementById("swap").textContent=pct(d.memory.swap_used_percent);bar("swapBar",d.memory.swap_used_percent);document.getElementById("swapMeta").textContent=`${bytes(d.memory.swap_used_bytes)} usado de ${bytes(d.memory.swap_total_bytes)}`;
    document.getElementById("uptime").textContent=up(d.uptime_seconds);document.getElementById("processes").textContent=`${d.processes.process_count||0} procesos activos`;
    const networkTotal=(d.network.rx_bytes||0)+(d.network.tx_bytes||0);let networkRate=0;if(previousNetwork&&d.timestamp>previousNetwork.timestamp){networkRate=Math.max(0,(networkTotal-previousNetwork.total)/(d.timestamp-previousNetwork.timestamp))}previousNetwork={timestamp:d.timestamp,total:networkTotal};document.getElementById("net").textContent=rate(networkRate);document.getElementById("netMeta").textContent=`RX ${bytes(d.network.rx_bytes)} · TX ${bytes(d.network.tx_bytes)}`;
    document.getElementById("efi").textContent=d.efi.mounted?"Montado":"No montado";document.getElementById("efiMeta").textContent=(d.efi.mounts||[]).map(x=>`${x.path} · ${pct(x.used_percent)}`).join(" | ")||"Sin partición EFI montada";
    list("disk",(d.disk||[]).map(x=>`<span>${x.label} · ${x.path}</span><strong>${pct(x.used_percent)} · ${bytes(x.free_bytes)} libre</strong>`));const sv=d.processes.services||{};list("services",Object.keys(sv).map(k=>`<span><span class="dot ${sv[k].running?"on":""}"></span> ${labels[k]||k}</span><strong>${sv[k].running?"Activo":"Inactivo"} · ${sv[k].count||0}</strong>`));list("temps",(d.temperatures||[]).map(x=>`<span>${x.name}</span><strong>${Number(x.celsius).toFixed(1)} °C</strong>`));list("ifaces",(d.network.interfaces||[]).map(x=>`<span>${x.name}</span><strong>RX ${bytes(x.rx_bytes)} · TX ${bytes(x.tx_bytes)}</strong>`));list("loads",[`<span>1 minuto</span><strong>${Number(d.cpu.load_avg_1m||0).toFixed(2)}</strong>`,`<span>5 minutos</span><strong>${Number(d.cpu.load_avg_5m||0).toFixed(2)}</strong>`,`<span>15 minutos</span><strong>${Number(d.cpu.load_avg_15m||0).toFixed(2)}</strong>`]);
    push("cpu",d.cpu.used_percent);push("ram",d.memory.used_percent);push("swap",d.memory.swap_used_percent);push("net",networkRate);document.getElementById("cpuNow").textContent=pct(d.cpu.used_percent);document.getElementById("ramNow").textContent=pct(d.memory.used_percent);document.getElementById("swapNow").textContent=pct(d.memory.swap_used_percent);document.getElementById("netNow").textContent=rate(networkRate);draw("chartCpu",history.cpu,"#f13811");draw("chartRam",history.ram,"#20d684");draw("chartSwap",history.swap,"#f59e0b");draw("chartNet",history.net,"#38bdf8",Math.max(...history.net,1));}catch(e){document.getElementById("updated").textContent="Sin conexión"}}
    refresh();setInterval(refresh,3000);addEventListener("resize",()=>{draw("chartCpu",history.cpu,"#f13811");draw("chartRam",history.ram,"#20d684");draw("chartSwap",history.swap,"#f59e0b");draw("chartNet",history.net,"#38bdf8",Math.max(...history.net,1))});
  </script>
</body>
</html>
        """
    )
