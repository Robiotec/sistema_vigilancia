import { elements, pageData } from "./dom.js";
import { PolygonEditor } from "./polygon-editor.js";
import { VideoPlayerController } from "./video-player.js";

const editor = new PolygonEditor({
  video: elements.video,
  overlay: elements.overlay,
  stage: elements.stage,
  output: elements.output,
  pointCount: elements.pointCount,
  videoSize: elements.videoSize,
  stateBadge: elements.stateBadge,
  copyFeedback: elements.copyFeedback,
  videoName: pageData.videoName,
});

const player = new VideoPlayerController({
  video: elements.video,
  playPauseButton: elements.playPauseButton,
  backwardButton: elements.backwardButton,
  forwardButton: elements.forwardButton,
  speedSelect: elements.speedSelect,
  timeReadout: elements.timeReadout,
  onMetadataLoaded: () => editor.syncVideoMetadata(),
});

function bindEditorEvents() {
  elements.overlay.addEventListener("click", (event) => {
    if (event.detail !== 1) {
      return;
    }

    editor.addPointFromEvent(event);
  });

  elements.overlay.addEventListener("dblclick", () => {
    editor.closePolygon();
  });

  elements.overlay.addEventListener("mousemove", (event) => {
    editor.updateHoverFromEvent(event);
  });

  elements.overlay.addEventListener("mouseleave", () => {
    editor.clearHover();
  });

  elements.closePolygonButton.addEventListener("click", () => {
    editor.closePolygon();
  });

  elements.undoPointButton.addEventListener("click", () => {
    editor.undoLastPoint();
  });

  elements.clearPolygonButton.addEventListener("click", () => {
    editor.clearPolygon();
  });

  elements.copyJsonButton.addEventListener("click", () => {
    void editor.copyJson();
  });

  window.addEventListener("resize", () => {
    editor.renderOverlay();
  });
}

editor.initialize();
player.initialize();
bindEditorEvents();

if (elements.video.readyState >= HTMLMediaElement.HAVE_METADATA) {
  editor.syncVideoMetadata();
  player.updateTimeReadout();
}
