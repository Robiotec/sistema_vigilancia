type RealtimeCameraFrameOptions = {
  viewerUrl: string;
  title: string;
  className?: string;
  muted?: boolean;
};

export class RealtimeCameraFrame {
  static create(options: RealtimeCameraFrameOptions): HTMLIFrameElement {
    const frame = document.createElement("iframe");
    frame.className = options.className ?? "rb-camera-frame";
    frame.loading = "eager";
    frame.allow = "autoplay; fullscreen; picture-in-picture";
    frame.referrerPolicy = "strict-origin-when-cross-origin";
    frame.title = options.title;
    frame.setAttribute("allowfullscreen", "");
    frame.srcdoc = this.document(options);
    return frame;
  }

  private static document(options: RealtimeCameraFrameOptions): string {
    const target = new URL(options.viewerUrl, window.location.href);
    const viewerBase = this.normalizedViewerBase(target);
    const readerUrl = new URL("reader.js", viewerBase);
    const whepUrl = new URL("whep", viewerBase);
    whepUrl.search = target.search;
    const muted = options.muted ?? true;

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#05070a;font-family:Arial,sans-serif}
#video{position:absolute;inset:0;width:100%;height:100%;background:#05070a}
#message{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box;text-align:center;color:#f8fafc;font-size:15px;font-weight:700;text-shadow:0 0 5px #000;pointer-events:none}
</style>
<script src="${this.escapeAttribute(readerUrl.toString())}"></script>
</head>
<body>
<video id="video"></video>
<div id="message"></div>
<script>
const video=document.getElementById("video");
const message=document.getElementById("message");
const whepUrl=${JSON.stringify(whepUrl.toString())};
let reader=null;
function friendly(value){
  const raw=String(value||"").toLowerCase();
  if(raw.includes("stream not found")||raw.includes("path not found")) return "La señal de esta cámara no está disponible en este momento.";
  if(raw.includes("unauthorized")||raw.includes("forbidden")) return "No se pudo autorizar el acceso al video de esta cámara.";
  if(raw.includes("timeout")||raw.includes("network")) return "No se pudo conectar con la señal de video. Reintentando...";
  return raw ? "La señal de video no está disponible. Reintentando..." : "";
}
function setMessage(value){
  const next=friendly(value);
  message.textContent=next;
  video.controls=!next;
}
window.addEventListener("load",()=>{
  video.autoplay=true;
  video.controls=true;
  video.playsInline=true;
  video.muted=${muted ? "true" : "false"};
  if(typeof MediaMTXWebRTCReader!=="function"){
    setMessage("No se pudo cargar el visor WebRTC.");
    return;
  }
  reader=new MediaMTXWebRTCReader({
    url:whepUrl,
    onError:(err)=>setMessage(err),
    onTrack:(evt)=>{
      setMessage("");
      video.srcObject=evt.streams[0];
      video.play().catch(()=>{});
    },
    onDataChannel:(evt)=>{evt.channel.binaryType="arraybuffer";}
  });
});
window.addEventListener("beforeunload",()=>{if(reader!==null) reader.close();});
</script>
</body>
</html>`;
  }

  private static normalizedViewerBase(target: URL): URL {
    const normalized = new URL(target.toString());
    const pathname = normalized.pathname || "/";
    const lastSegment = pathname.split("/").filter(Boolean).pop() || "";
    if (!pathname.endsWith("/") && !/\.[a-z0-9]+$/i.test(lastSegment)) {
      normalized.pathname = `${pathname}/`;
    }
    return normalized;
  }

  private static escapeAttribute(value: string): string {
    return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }
}
